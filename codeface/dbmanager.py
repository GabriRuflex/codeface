#! /usr/bin/env python
# This file is part of Codeface. Codeface is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Copyright 2013 by Siemens AG, Wolfgang Mauerer <wolfgang.mauerer@siemens.com>
# All Rights Reserved.

# Thin sql database wrapper

import MySQLdb as mdb
from datetime import datetime
from logging import getLogger;
from contextlib import contextmanager

import codeface.issueanalyzer.common_utils as utils

# create logger
log = getLogger(__name__)

@contextmanager
def _log_db_error(action, args=None):
    try:
        yield
    except mdb.Error as e:
        if args:
            try:
                action = action.format(args)
            except:
                pass
        log.critical('MySQL error {e[0]} during "{action}": {e[1]}'
                     ''.format(e=e.args, action=action))
        raise


class DBManager:
    """This class provides an interface to the codeface sql database."""

    def __init__(self, conf):
        try:
            self.con = None
            self.con = mdb.Connection(host=conf["dbhost"],
                                      port=conf["dbport"],
                                      user=conf["dbuser"],
                                      passwd=conf["dbpwd"],
                                      db=conf["dbname"])
            log.debug(
                "Establishing MySQL connection to "
                "{c[dbuser]}@{c[dbhost]}:{c[dbport]}, DB '{c[dbname]}'"
                    .format(c=conf))
        except mdb.Error as e:
            log.critical(
                "Failed to establish MySQL connection to "
                "{c[dbuser]}@{c[dbhost]}:{c[dbport]}, DB '{c[dbname]}'"
                ": {e[1]} ({e[0]})"
                "".format(c=conf, e=e.args))
            raise
        self.cur = self.con.cursor()

        max_packet_size = 1024 * 1024 * 256
        self.doExec("SET GLOBAL max_allowed_packet=%s", (max_packet_size,))

    def __del__(self):
        if self.con != None:
            self.con.close()

    def doExec(self, stmt, args=None):
        with _log_db_error(stmt, args):
            while True:
                try:
                    if isinstance(args, list):
                        res = self.cur.executemany(stmt, args)
                    else:
                        res = self.cur.execute(stmt, args)
                    return res
                except mdb.OperationalError as dbe:
                    log.info("DBE args: " + str(dbe.args))
                    if dbe.args[0] == 1213:  # Deadlock! retry...
                        log.warning("Recoverable deadlock in MySQL - retrying.")
                    elif dbe.args[0] == 2006:  # Server gone away...
                        log.warning("MySQL Server gone away, trying to reconnect.")
                        self.con.ping(True)
                    elif dbe.args[0] == 2013:  # Lost connection to MySQL server during query...
                        log.warning("Lost connection to MySQL server during query, trying to reconnect.")
                        self.con.ping(True)
                    else:
                        raise

    def doFetchAll(self):
        with _log_db_error("fetchall"):
            return self.cur.fetchall()

    def doCommit(self):
        with _log_db_error("commit"):
            return self.con.commit()

    def doExecCommit(self, stmt, args=None):
        self.doExec(stmt, args)
        self.doCommit()

    # NOTE: We don't provide any synchronisation since by assumption,
    # a single project is never analysed from two threads.
    def getProjectID(self, name, analysisMethod):
        """
        Return the project ID of the given name/analysisMethod combination.
        If the project does not exist yet in the database, it is created.
        """
        self.doExec("SELECT id FROM project WHERE name=%s "
                    "AND analysisMethod=%s", (name, analysisMethod))
        if self.cur.rowcount == 0:
            # Project is not contained in the database
            log.devinfo("Creating new project {}/{}".
                        format(name, analysisMethod))
            self.doExecCommit("INSERT INTO project (name, analysisMethod) " +
                              "VALUES (%s, %s);", (name, analysisMethod))
            self.doExec("SELECT id FROM project WHERE name=%s;", (name,))
        elif self.cur.rowcount > 1:
            raise Exception("Duplicate projects {}/{} in database!".
                            format(name, analysisMethod))
        pid = self.doFetchAll()[0][0]
        log.devinfo("Using project {}/{} with ID {}".
                    format(name, analysisMethod, pid))
        return pid

    def get_project(self, pid):
        self.doExec("SELECT name, analysisMethod FROM project"
                    " WHERE id=%s", pid)
        if self.cur.rowcount == 0:
            raise Exception("Project id {} not found!".format(pid))
        return self.doFetchAll()[0]

    def get_edgelist(self, cid):
        self.doExec("SELECT fromId, toId, weight FROM edgelist \
                    WHERE clusterId={}".format(cid))
        if self.cur.rowcount == 0:
            raise Exception("Cluster id {} not found!".format(cid))
        return self.doFetchAll()

    def get_file_dev(self, project_id, range_id):
        self.doExec("SELECT * FROM (SELECT id, commitHash, commitDate, author, description " \
                    "FROM commit WHERE projectId={} AND releaseRangeId={}) AS Commits " \
                    "INNER JOIN (SELECT file, commitId, SUM(size) AS fileSize " \
                    "FROM commit_dependency GROUP BY commitId, file) AS commitFileLOC " \
                    "ON Commits.id=commitFileLOC.commitId ORDER BY " \
                    "commitFileLOC.file, commitFileLOC.commitId".format(project_id, range_id))

        if self.cur.rowcount == 0:
            raise Exception("Could not obtain file-dev information for project {} "\
                            "(release range {}!".format(project_id, range_id))
        return self.doFetchAll()

    def get_release_ranges(self, project_id):
        self.doExec("SELECT id FROM release_range \
                    WHERE projectId={}".format(project_id))
        if self.cur.rowcount == 0:
            raise Exception("No release ranges found for project {}!"
                            .format(project_id))
        return [range_entry[0] for range_entry in self.doFetchAll()]

    def get_cluster_id(self, pid, release_range_id=None):
        if release_range_id:
            self.doExec("SELECT id FROM cluster WHERE clusterNumber=-1 \
                        AND projectId={} AND releaseRangeId={}"
                        .format(pid, release_range_id))
        else:
            self.doExec("SELECT id FROM cluster WHERE clusterNumber=-1 \
                        AND projectId={}".format(pid))
        if self.cur.rowcount == 0:
            raise Exception("Cluster from project {} not found!".format(pid))
        return self.doFetchAll()[0][0]

    def get_project_persons(self, pid):
        self.doExec("SELECT id, name FROM person \
                    WHERE projectId={}".format(pid))
        if self.cur.rowcount == 0:
            raise Exception("Persons from project {} not found!".format(pid))
        return (self.doFetchAll())

    def getTagID(self, projectID, tag, type):
        """Determine the ID of a tag, given its textual form and the type"""
        self.doExec("SELECT id FROM release_timeline WHERE projectId=%s " +
                    "AND tag=%s AND type=%s", (projectID, tag, type))
        if self.cur.rowcount != 1:
            raise Exception("Tag '{}' of type {} is {} times in the DB!".
                            format(tag, type, self.cur.rowcount))
        return self.doFetchAll()[0][0]

    def getCommitId(self, projectId, commitHash):
        self.doExec("SELECT id FROM commit" +
                    " WHERE commitHash=%s AND projectId=%s"
                    , (commitHash, projectId))
        if self.cur.rowcount == 0:
            raise Exception("Commit from project {} not found!".
                            format(projectId))
        return self.doFetchAll()[0][0]

    def getRevisionID(self, projectID, tag):
        return self.getTagID(projectID, tag, "release")

    def getRCID(self, projectID, tag):
        return self.getTagID(projectID, tag, "rc")

    def getReleaseRangeID(self, projectID, revisionIDs):
        """Given a pair of release IDs, determine the release range ID"""
        self.doExec("SELECT id FROM release_range WHERE projectId=%s " +
                    "AND releaseStartId=%s AND releaseEndId=%s",
                    (projectID, revisionIDs[0], revisionIDs[1]))
        if self.cur.rowcount != 1:
            raise Exception("Release range from '{r[0]}' to '{r[1]}' is {c} "
                            "times in the DB!".
                            format(r=revisionIDs, c=self.cur.rowcount))
        return self.doFetchAll()[0][0]

    def getProjectTimeRange(self, pid):
        """Given a project ID, determine the start and end date of available VCS data.
           Returns a tuple with start end end date in the form YYYY-MM-DD"""
        self.doExec("SELECT MIN(date_start) FROM revisions_view "
                    "WHERE projectId={}".format(pid))
        if self.cur.rowcount == 0:
            raise Exception("No start date for pid {} found!".format(pid))
        date_start = self.doFetchAll()[0][0].strftime("%Y-%m-%d")

        self.doExec("SELECT MAX(date_end) FROM revisions_view "
                    "WHERE projectId={}".format(pid))
        if self.cur.rowcount == 0:
            raise Exception("No end date for pid {} found!".format(pid))
        date_end = self.doFetchAll()[0][0].strftime("%Y-%m-%d")

        return (date_start, date_end)

    def get_commit_cdate(self, pid, hash):
        """Given a project ID and a commit hash, obtain the commit date
           in format YYYY-MM-DD"""
        self.doExec("SELECT commitDate FROM commit "
                    "WHERE projectId={} and commitHash='{}'".format(pid, hash))
        if self.cur.rowcount == 0:
            raise Exception("No date found for commit {} (pid {}) found!".format(hash, pid))
        date = self.doFetchAll()[0][0].strftime("%Y-%m-%d")

        return (date)

    def get_release_range(self, project_id, range_id):
        self.doExec(
            "SELECT st.tag, nd.tag, rc.tag FROM release_range "
            "LEFT JOIN release_timeline AS st ON st.id=releaseStartId "
            "LEFT JOIN release_timeline AS nd ON nd.id=releaseEndId "
            "LEFT JOIN release_timeline AS rc ON rc.id=releaseRCStartId "
            "WHERE release_range.projectId=%s AND release_range.id=%s",
            (project_id, range_id))
        ranges = self.doFetchAll()
        if self.cur.rowcount == 0:
            raise Exception("Range id {} not found!".format(project_id))
        return ranges[0]

    def update_release_timeline(self, project, tagging, revs, rcs,
                                recreate_project=False):
        '''
        For a project, update the release timeline table with the given
        revisions. If existing releases/rcs from the timeline are not in
        order, the conservative approach is taken and the whole project is
        recreated to avoid inconsistencies.

        Returns true if the project had to be recreated.
        '''
        assert len(revs) >= 2
        assert len(revs) == len(rcs)
        rcs = [rc if rc else rev for rc, rev in zip(rcs, revs)]
        pid = self.getProjectID(project, tagging)

        if not recreate_project:
            # First check if the release timeline is sane and in order
            self.doExec("SELECT tag FROM release_timeline WHERE projectId=%s "
                        "AND type='release' ORDER BY id", (pid,))
            tags = [tag for (tag,) in self.doFetchAll()]
            if len(set(tags)) != len(tags):
                log.error("Database corrupted: Duplicate release entries in "
                          "release_timeline! Recreating project.")
                recreate_project = True
            if len(tags) == 0:
                recreate_project = True

        # Check that the tags are in the same order
        if not recreate_project:
            for i, tag in enumerate(tags):
                if i >= len(revs):
                    log.warning("List of revisions to analyse was shortened.")
                    break
                if revs[i] != tag:
                    log.error("Release number {} changed tag from {} to "
                              "{}. Recreating project.".
                              format(i, tag, revs[i]))
                    recreate_project = True
                    break

        # Check that the RC tags are in order
        if not recreate_project:
            self.doExec("SELECT tag FROM release_timeline WHERE "
                        "projectId=%s AND type='rc' ORDER BY id", (pid,))
            rctags = [tag for (tag,) in self.doFetchAll()]
            if len(set(rctags)) != len(rctags):
                log.error("Database corrupted: Duplicate RC entries in "
                          "release_timeline! Recreating project.")
                recreate_project = True

        # Check for changes in release candidates
        # Note that the first RC is unused, since it refers to the end
        # of a previous period
        if not recreate_project:
            for i, tag in enumerate(rctags):
                if i + 1 >= len(rcs):
                    log.warning("List of release candidates to analyse "
                                "was shortened.")
                    break
                if rcs[i + 1] != tag:
                    log.error("Release candidate number {} changed tag "
                              "from {} to {}. Recreating project.".
                              format(i, tag, rcs[i + 1]))
                    recreate_project = True
                    break

        # Go through the release ranges and check if they have changed
        if not recreate_project:
            self.doExec(
                "SELECT st.tag, nd.tag, rc.tag FROM release_range "
                "LEFT JOIN release_timeline AS st ON st.id=releaseStartId "
                "LEFT JOIN release_timeline AS nd ON nd.id=releaseEndId "
                "LEFT JOIN release_timeline AS rc ON rc.id=releaseRCStartId "
                "WHERE release_range.projectId=%s ORDER BY release_range.id",
                (pid,))
            ranges = self.doFetchAll()
            if len(set(ranges)) != len(tags) - 1:
                log.error("Database corrupted: Number of release ranges"
                          " does not match number of release tags!")
                recreate_project = True

            for i, (start, end, rc) in enumerate(self.doFetchAll()):
                if i + 1 >= len(revs) or recreate_project:
                    # List of revisions to analyse was shortened
                    break
                if (start, end) != (revs[i], revs[i + 1]):
                    log.error("Release range {} changed from {} to {}."
                              " Recreating project.".
                              format(i, (start, end), (revs[i], revs[i + 1])))
                    recreate_project = True
                    break
                if rc != rcs[i + 1]:
                    log.error("Release candidate {} changed from {} to {}."
                              " Recreating project.".
                              format(i, rc, rcs[i + 1]))
                    recreate_project = True
                    break

        # Recreate project if necessary
        if recreate_project:
            # This should ripple through the database and delete
            # all referencing entries for project
            log.warning("Deleting and re-creating project {}/{}.".
                        format(project, tagging))
            self.doExecCommit("DELETE FROM `project` WHERE id=%s", (pid,))
            pid = self.getProjectID(project, tagging)
            tags = []
            rctags = []

        # at this point we have verified that the first len(tags)
        # entries are identical
        new_ranges_to_process = []
        if len(revs) > len(tags):
            n_new = len(revs) - len(tags)
            log.info("Adding {} new releases...".format(n_new))
            previous_rev = None
            if len(tags) > 0:
                previous_rev = tags[-1]
            for rev, rc in zip(revs, rcs)[len(tags):]:
                self.doExecCommit("INSERT INTO release_timeline "
                                  "(type, tag, projectId) "
                                  "VALUES (%s, %s, %s)",
                                  ("release", rev, pid))

                if previous_rev is not None and rc:
                    self.doExecCommit("INSERT INTO release_timeline "
                                      "(type, tag, projectId) "
                                      "VALUES (%s, %s, %s)",
                                      ("rc", rc, pid))

                if previous_rev is not None:
                    startID = self.getRevisionID(pid, previous_rev)
                    endID = self.getRevisionID(pid, rev)
                    if rc:
                        rcID = self.getRCID(pid, rc)
                    else:
                        rcID = "NULL"
                    self.doExecCommit("INSERT INTO release_range "
                                      "(releaseStartId, releaseEndId, "
                                      "projectId, releaseRCStartId) "
                                      "VALUES (%s, %s, %s, %s)",
                                      (startID, endID, pid, rcID))
                    new_ranges_to_process.append(self.getReleaseRangeID(pid,
                                                                        (startID, endID)))
                previous_rev = rev
        # now we are in a well-defined state.
        # Return the ids of the release ranges we have to process
        return new_ranges_to_process

    def get_issue_project(self, url, name, p1, p2, recreateIfExist = False):
        """
        Return the project ID of the given url/name combination.
        If the project does not exist yet in the database, it is created.
        """
        # Check if project already exists
        self.doExec("SELECT projectId FROM issue_project WHERE url=%s AND name=%s;", (url, name))
        if self.cur.rowcount > 0:
            if not recreateIfExist:
                # Just return the project ID
                return self.doFetchAll()[0][0]
            else:
                # Drop data in database of the current project
                self.reset_issue_database(self.doFetchAll()[0][0])
        
        # Create a new project
        self.doExecCommit("INSERT INTO issue_project (url, name, priorityField1, priorityField2) "
                          "VALUES (%s, %s, %s, %s)", (url, name, p1, p2))
        self.doExec("SELECT projectId FROM issue_project WHERE url=%s AND name=%s;", (url, name))
        pid = self.doFetchAll()[0][0]

        return pid

    def add_issue_data(self, issue_data):
        """
        Add an issue of the project.
        """        
        try:
            self.doExecCommit("INSERT INTO issue_data "
                              "(issueId, projectId, summary, component, creationTime, creator, assignedTo, spentTime, priority, priorityValue, "
                              "severity, severityValue, status, resolution, isOpen, votes, commentCount, keywords, lastResolved, realAssignee) "
                              "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", issue_data)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting issue data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting issue data")
        return

    def add_issue_developer(self, issue_developer):
        """
        Add a developer of the project.
        """
        try:
            self.doExecCommit("INSERT INTO issue_developer "
                      "(name, projectId, developerId, realName) "
                      "VALUES (%s, %s, %s, %s)", issue_developer)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting developer data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting developer data")
        return

    def add_issue_attachment(self, issue_attachment):
        """
        Add an attachment related to an issue of the project.
        """
        try:
            self.doExecCommit("INSERT INTO issue_attachment "
                      "(attachmentId, projectId, issueId, creator, creationTime, isObsolete, isPatch, isPrivate, size, positiveReviews) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", issue_attachment)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting attachment data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting attachment data")
        return

    def add_issue_cclist(self, issue_cclist):
        """
        Add a list of developers following an issue of the project.
        """
        try:
            self.doExecCommit("INSERT INTO issue_cclist "
                      "(issueId, projectId, developerName) "
                      "VALUES (%s, %s, %s)", issue_cclist)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting CC developers data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting CC developers data")
        return

    def add_issue_comment(self, issue_comments):
        """
        Add a comment related to an issue of the project.
        """
        try:
            self.doExecCommit("INSERT INTO issue_comment "
                      "(commentId, projectId, issueId, author, time, rawText) "
                      "VALUES (%s, %s, %s, %s, %s, %s)", issue_comments)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting comments data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting comments data")
        return

    def add_issue_dependencies(self, issue_dependencies):
        """
        Add a dependency related to an issue of the project.
        """
        try:
            self.doExecCommit("INSERT INTO issue_dependencies "
                              "(issueId, projectId, relatedIssueId, relationType) "
                              "VALUES (%s, %s, %s, %s)", issue_dependencies)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting dependencies data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting dependencies data")
        return

    def add_issue_history(self, issue_history):
        """
        Add an history's change related to an issue of the project.
        """
        try:
            self.doExecCommit("INSERT INTO issue_history "
                      "(issueId, projectId, who, time, added, removed, attachmentId, fieldName) "
                      "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", issue_history)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting history data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting history data")
        return

    def add_issue_assignment(self, issue_assignment):
        """
        Add the assignee to an issue of the project.
        """
        try:
            self.doExecCommit("INSERT INTO issue_assignment "
                      "(issueId, projectId, developerName) "
                      "VALUES (%s, %s, %s)", issue_assignment)
        except mdb.MySQLError as e:
            if hasattr(e, 'message'):
                log.debug("Error when inseriting history data. Message: {}".format(e.message))
            else:
                log.debug("Error when inseriting history data")
        return

    def get_data_stored(self, projectId):
        """
        Get the developers' assignment data related to the project.
        """
        issue_tables = dict()

        sqlQuery = "select issueId, projectId, summary, component, creationTime, creator, assignedTo, priority, severity, " \
                   "status, resolution, isOpen, votes, commentCount, keywords, lastResolved from issue_data where projectId = {}".format(projectId)
        self.doExec(sqlQuery)
        issue_tables[utils.KEY_ITEMS_BUGS] = self.doFetchAll()

        sqlQuery = "select name, realName, projectId, developerId  " \
                   "from issue_developer where projectId = {}".format(projectId)
        self.doExec(sqlQuery)
        issue_tables[utils.KEY_ITEMS_DEVELOPERS] = self.doFetchAll()

        sqlQuery = "select attachmentId, projectId, issueId, creator, creationTime, isObsolete, isPatch, isPrivate, size, positiveReviews " \
                   "from issue_attachment where projectId = {}".format(projectId)
        self.doExec(sqlQuery)
        issue_tables[utils.KEY_ITEMS_ATTACHMENTS] = self.doFetchAll()

        sqlQuery = "select commentId, projectId, issueId, author, time, rawText " \
                   "from issue_comment where projectId = {}".format(projectId)
        self.doExec(sqlQuery)
        issue_tables[utils.KEY_ITEMS_COMMENTS] = self.doFetchAll()

        sqlQuery = "select issueId, projectId, who, time, added, removed, attachmentId, fieldName " \
                   "from issue_history where projectId = {}".format(projectId)
        self.doExec(sqlQuery)
        issue_tables[utils.KEY_ITEMS_HISTORY] = self.doFetchAll()

        sqlQuery = "select issueId, projectId, relatedIssueId, relationType " \
                   "from issue_dependencies where projectId = {}".format(projectId)
        self.doExec(sqlQuery)
        issue_tables[utils.KEY_ITEMS_RELATIONS] = self.doFetchAll()

        return issue_tables

    def get_view_assignment(self, projectId, queryType):
        """
        Get the developers' assignment data related to the project.
        """
        sqlQuery = ""
        if queryType == utils.QUERY_TYPE_ALL_ASSIGNMENTS:
            sqlQuery = "SELECT * FROM view_assignment \
                    WHERE projectId={}".format(projectId)
        elif queryType == utils.QUERY_TYPE_ASSIGNMENTS_STATS:
            sqlQuery = "select issueId, component, priority, severity, avg(issueAssigned) as 'avgIssueAssigned', avg(devAvgTime) as 'avgDevAvgTime', " \
                    "avg(numCommentPosted) as 'avgNumCommentPosted', avg(numAttachmentPosted) as 'avgNumAttachmentPosted', " \
                    "avg(positiveReviews), avg(sizeAttachmentPosted) from view_assignment where projectId = {} " \
                    "GROUP BY issueId, component, priority, severity".format(projectId)
        self.doExec(sqlQuery)
        if self.cur.rowcount == 0:
            log.debug("Data from project {} not found!".format(projectId))
        return (self.cur)

    def get_view_reality_check(self, projectId):
        """
        Get the developers' assignment real check data related to the project.
        """
        sqlQuery = "select TP, FP, FN " \
                   "from view_reality_check where projectId = {}".format(projectId)
        self.doExec(sqlQuery)
        if self.cur.rowcount == 0:
            log.debug("Data from project {} not found!".format(projectId))
        return (self.cur)

    def get_issue_developer_statistics(self, projectId, developerName, isOpen):
        """
        Get the developers' statistics data related to the project.
        """
        self.doExec("SELECT stat.spentTime " \
                    "FROM view_developer_statistic stat " \
                    "WHERE stat.projectId = {0} and stat.assignedTo = '{1}' and stat.isOpen = {2}".format(projectId, developerName, isOpen))

        result = 0
        if self.cur.rowcount == 0:
            log.debug("Data from project {} not found!".format(projectId))
        else:
            result = self.cur.fetchone()[0]
        return (result)

    def reset_issue_database(self, pid = ""):
        """
        Reset all the data stored on the database.
        """
        if pid == "":
            sql_statement = "SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;" \
                            "SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;" \
                            "SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='TRADITIONAL,ALLOW_INVALID_DATES';" \
                            "TRUNCATE codeface.issue_project;" \
                            "TRUNCATE codeface.issue_data;" \
                            "TRUNCATE codeface.issue_developer;" \
                            "TRUNCATE codeface.issue_attachment;" \
                            "TRUNCATE codeface.issue_cclist;" \
                            "TRUNCATE codeface.issue_comment;" \
                            "TRUNCATE codeface.issue_dependencies;" \
                            "TRUNCATE codeface.issue_history;" \
                            "TRUNCATE codeface.issue_developer_ranks_view;" \
                            "TRUNCATE codeface.issue_bug_ranks_view;" \
                            "SET SQL_MODE=@OLD_SQL_MODE;" \
                            "SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;" \
                            "SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;"
            self.doExec(sql_statement)
        else:
            sql_statement = str("DELETE FROM codeface.issue_project WHERE projectId = {pid};").format(pid=pid)
            self.doExecCommit(sql_statement)

def tstamp_to_sql(tstamp):
    """Convert a Unix timestamp into an SQL compatible DateTime string"""
    return (datetime.utcfromtimestamp(tstamp).strftime("%Y-%m-%d %H:%M:%S"))

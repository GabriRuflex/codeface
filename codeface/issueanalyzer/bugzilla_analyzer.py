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
# Copyright 2013 by Siemens AG, Johannes Ebke <johannes.ebke.ext@siemens.com>
# All Rights Reserved.

"""
Bugzilla issue analyzer module
"""

import requests
from datetime import datetime, timedelta
from logging import getLogger; log = getLogger(__name__)

import codeface.issueanalyzer.common_utils as utils

from codeface.configuration import Configuration
from codeface.dbmanager import DBManager
from codeface.util import BatchJobPool

SHOW_DEBUG = 0
MORE_DEVELOPERS = 0

# Definitions of query parameters
QUERY_BUG_OPEN_NOT_ASSIGNED = 0
QUERY_BUG_CLOSED_FIXED = 1
QUERY_BUG_ASSIGNED = 2
QUERY_ATTACHMENT_FROM_ID = 3
QUERY_ATTACHMENT_OF_BUGLIST = 4
QUERY_BUG_FROM_ID = 5
QUERY_DEVELOPER_FROM_EMAIL = 6
QUERY_DEVELOPER_FROM_EMAIL_LIST = 7
QUERY_COMMENT_OF_BUG = 8
QUERY_COMMENT_OF_BUGLIST = 9
QUERY_HISTORY_OF_BUG = 10
QUERY_HISTORY_OF_BUGLIST = 11
QUERY_BUG_FROM_LIST = 12
QUERY_BUG_FROM_ID_OR_LIST = 13

# SQL results
BUG_ID = 0
PROJECT_ID = 1
COMPONENT = 2
PRIORITY = 3
SEVERITY = 4

STATS_PRIORITY = 2
STATS_SEVERITY = 3
AVG_NUM_ASSIGNED = 4
AVG_DEV_AVG_TIME = 5
AVG_NUM_COMMENT = 6
AVG_NUM_ATTACHMENT = 7
AVG_REVIEWS = 8
AVG_SIZE_ATTACHMENT = 9

DEVELOPER = 5
IS_OPEN = 6
REVIEWS = 7
NUM_ASSIGNED = 8
NUM_ATTACHMENT = 9
NUM_COMMENT = 10
SIZE_ATTACHMENT = 11
DEV_AVG_TIME = 12
BUG_AVG_ETA = 13

def getQueryParams(conf, queryType, idParam = [], bugStatus = []):
    """Function to build the REST query

    Get the project configuration the query type and all the
    specific query parameters, then creates and returns the query.

    Args:
        conf(codeface.configuration.Configuration): Path of the Codeface configuration file
        queryType(int): Path of the project configuration file
            QUERY_BUG_OPEN_NOT_ASSIGNED:
            QUERY_BUG_CLOSED_FIXED:
            QUERY_BUG_ASSIGNED:
            QUERY_ATTACHMENT_FROM_ID:
            QUERY_ATTACHMENT_OF_BUGLIST:
            QUERY_BUG_FROM_ID:
            QUERY_DEVELOPER_FROM_EMAIL:
            QUERY_DEVELOPER_FROM_EMAIL_LIST:
            QUERY_COMMENT_OF_BUG:
            QUERY_COMMENT_OF_BUGLIST:
            QUERY_HISTORY_OF_BUG:
            QUERY_HISTORY_OF_BUGLIST:
            QUERY_BUG_FROM_LIST:
            QUERY_BUG_FROM_ID_OR_LIST:
        idParam(tuple): Single or list of objects' id (bug, developer, attachment, comment, history)
        bugStatus(int): Set 0 for fixed bugs, 1 for open ones

    Returns (str): The REST string that will be used to query the bug tracker

    """
    params =  ""
    if queryType == QUERY_BUG_OPEN_NOT_ASSIGNED:
        # Get bug opened and not assigned in the last [x] days
        date = (datetime.today() - timedelta(days=conf["issueAnalyzerBugOpenedDays"])).strftime("%Y-%m-%d")
        params = str("{}rest/bug?include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,creator,comment_count,depends_on,keywords,is_open,priority,resolution,severity,summary,status,votes" \
                     "&bug_status=NEW&bug_status=ASSIGNED&is_private=&chfield=[Bug creation]&chfieldfrom={}&chfieldto=Now" \
                     "&email1=nobody%40mozilla.org&emailassigned_to1=1&emailtype1=exact&priority={}&priority={}&product={}&resolution=---").format(
                         conf['issueAnalyzerURL'], date, conf["issueAnalyzerPriority1"], conf["issueAnalyzerPriority2"], conf["issueAnalyzerProduct"])
    elif queryType == QUERY_BUG_CLOSED_FIXED:
        # Get bugs fixed and resolved in the last [x] days (used to get a list of active developers)
        date = (datetime.today() - timedelta(days=conf["issueAnalyzerBugFixedDays"])).strftime("%Y-%m-%d")
        params = str("{}rest/bug?include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,creator,comment_count,depends_on,keywords,is_open,priority,resolution,severity,summary,status,votes" \
                     "&chfield=resolution&chfieldfrom={}&chfieldto=Now&chfieldvalue=FIXED&email1=nobody%40mozilla.org&emailassigned_to1=1&emailtype1=notequals" \
                     "&priority={}&priority={}&product={}&resolution=FIXED").format(
                         conf['issueAnalyzerURL'], date, conf["issueAnalyzerPriority1"], conf["issueAnalyzerPriority2"], conf["issueAnalyzerProduct"])
    elif queryType == QUERY_BUG_ASSIGNED:
        # Get bugs assigned in the last [x] days (used to get a list of active developers)
        date = (datetime.today() - timedelta(days=conf["issueAnalyzerBugFixedDays"])).strftime("%Y-%m-%d")
        params = str("{}rest/bug?include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,creator,comment_count,depends_on,keywords,is_open,priority,resolution,severity,summary,status,votes" \
                     "&chfield=assigned_to&chfieldfrom={}&chfieldto=Now&email1=nobody%40mozilla.org&emailassigned_to1=1&emailtype1=notequals" \
                     "&priority={}&priority={}&product={}&resolution=---").format(
                         conf['issueAnalyzerURL'], date, conf["issueAnalyzerPriority1"], conf["issueAnalyzerPriority2"], conf["issueAnalyzerProduct"])
    elif queryType == QUERY_ATTACHMENT_FROM_ID:
        # Get attachment using its ID
        params = str("{}rest/bug/attachment/{}?include_fields=bug_id,creation_time,creator,flags,id,is_obsolete,is_patch,is_private,last_change_time,size").format(
            conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_ATTACHMENT_OF_BUGLIST:
        # Get attachment using bug ID list
        if type(idParam) is list:
            firstBug = str(idParam[0])
            idParam = "&ids=".join(str(x) for x in idParam)
            params = str("{}rest/bug/{}/attachment?ids={}&include_fields=bug_id,creation_time,creator,flags,id,is_obsolete,is_patch,is_private,last_change_time,size").format(
            conf['issueAnalyzerURL'], firstBug, idParam)
        else:
            params = str("{}rest/bug/{}/history").format(conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_BUG_FROM_ID:
        # Get bug using its ID
        params = str("{}rest/bug/{}?include_fields=assigned_to,creation_time,id,is_open,last_change_time,priority,severity,summary,status").format(
            conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_DEVELOPER_FROM_EMAIL:
        # Get developer using his/her email
        params = str("{}rest/user?names={}&include_fields=email,id,name,real_name").format(conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_DEVELOPER_FROM_EMAIL_LIST:
        # Get developer using a single email or a list
        if type(idParam) is set:
            idParam = "&names=".join(str(x) for x in idParam)
        params = str("{}rest/user?names={}&include_fields=email,id,name,real_name").format(conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_COMMENT_OF_BUG:
        # Get bug comment using bug ID
        params = str("{}rest/bug/{}/comment?include_fields=attachment_id,author,bug_id,creation_time,id,raw_text&is_private=false").format(conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_COMMENT_OF_BUGLIST:
        # Get comments using bug ID list
        if type(idParam) is list:
            firstBug = str(idParam[0])
            idParam = "&ids=".join(str(x) for x in idParam)
            params = str("{}rest/bug/{}/comment?ids={}&include_fields=attachment_id,author,bug_id,creation_time,id,raw_text&is_private=false").format(
            conf['issueAnalyzerURL'], firstBug, idParam)
        else:
            params = str("{}rest/bug/{}/comment?include_fields=attachment_id,author,bug_id,creation_time,id,raw_text").format(conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_HISTORY_OF_BUG:
        # Get bug history using bug ID
        params = str("{}rest/bug/{}/history").format(conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_HISTORY_OF_BUGLIST:
        # Get history using bug ID list
        if type(idParam) is list:
            firstBug = str(idParam[0])
            idParam = "&ids=".join(str(x) for x in idParam)
            params = str("{}rest/bug/{}/history?ids={}").format(
            conf['issueAnalyzerURL'], firstBug, idParam)
        else:
            params = str("{}rest/bug/{}/history").format(conf['issueAnalyzerURL'], idParam)
    elif queryType == QUERY_BUG_FROM_LIST:
        # Get bug list using bug ID
        idParam = ",".join(idParam)
        bugStatus = "__open__" if (bugStatus == 1) else "__closed__" if (bugStatus == 0) else {}
        params = str("{}rest/bug?id={}&bug_status={}&include_fields=id").format(conf['issueAnalyzerURL'], idParam, bugStatus)
    elif queryType == QUERY_BUG_FROM_ID_OR_LIST:
        # Get bug using its ID or list
        bugStatus = "__open__" if (bugStatus == 1) else "__closed__" if (bugStatus == 0) else {}
        if type(idParam) is set:
            idParam = ",".join(str(x) for x in idParam)
        params = str("{}rest/bug?id={}&bug_status={}&include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,comment_count,depends_on,is_confirmed,is_open,last_change_time,priority,severity,summary,status,votes").format(
            conf['issueAnalyzerURL'], idParam, bugStatus)
    return params

def scratch(issueAnalyzer):
    """Function to scratch the bugtracker and get data

    Get the project configuration, query the bugtracker
    and then update the given dicts.

    Args:
       issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to update

    Returns None

    """
    log.info("Issue analyzer is scratching via Bugzilla module.")
    restResult = dict()

    urlResult = dict()
    bugResult = dict()
    devResult = dict()
    attachmentResult = dict()
    commentResult = dict()
    historyResult = dict()
    relationResult = dict()

    conf = issueAnalyzer.conf

    # Get all open bugs not assigned
    result = scratchBugOpenNotAssigned(conf)
    if result.ok:
        restResult = result.json()

        log.info(str("Bug not assigned and open. Bugs: {}. Byte: {}.").format(len(result.json()["bugs"]),len(result.content)))
    else:
        log.info("Bug not assigned and open: connection error.")

    # Store the bugs url
    urlResult[utils.KEY_ITEMS_BUGS] = result.url
    
    # Get and append all assigned open bugs
    result = scratchBugAssigned(conf)
    if result.ok:
        restResult["bugs"] = restResult["bugs"] + result.json()["bugs"]

        log.info(str("Bug assigned and open. Bugs: {}. Byte: {}.").format(len(result.json()["bugs"]),len(result.content)))
    else:
        log.info("Bug assigned and open: connection error.")

    # Get and append all assigned fixed bugs
    result = scratchBugClosedFixed(conf)
    if result.ok:
        restResult["bugs"] = restResult["bugs"] + result.json()["bugs"]

        log.info(str("Bug assigned and fixed. Bugs: {}. Byte: {}.").format(len(result.json()["bugs"]),len(result.content)))
    else:
        log.info("Bug assigned and fixed: connection error.")

    # Store the developers url
    urlResult[utils.KEY_ITEMS_DEVELOPERS] = result.url

    # Parse the bug results extracting the developers informations
    deps = set()
    num = len(restResult["bugs"])
    for bug in restResult["bugs"]:
        dev = bug.pop("assigned_to_detail")
        devResult[dev["name"]] = dev

        if MORE_DEVELOPERS:
            dev = bug.pop("creator_detail")
            devResult[dev["name"]] = dev

            devs = bug.pop("cc_detail")
            for dev in devs:
                devResult[dev["name"]] = dev
        
        bugResult[bug["id"]] = bug

        # Get all dependencies of open bugs
        if bug["is_open"]:
            for dep in bug["depends_on"]:
                deps.add(dep)

    # Check if dependecies of open bugs are fixed
    c = 0
    result = scratchBugIdOrList(conf, deps, bugStatus = 1)
    if result.ok:
        restResult = result.json()
        num = len(restResult["bugs"])
        for bug in restResult["bugs"]:
            idsBlocked = bug["blocks"]

            # Remove the bugs with dependencies unresolved
            for idBlocked in idsBlocked:
                if (idBlocked in bugResult.keys()) and bugResult[idBlocked]["is_open"]:
                    c = c + 1
                    del bugResult[idBlocked]

        log.info(str("Dependencies. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}.").format(num,num-c,c,len(result.content)))
    else:
        log.info("Dependencies: connection error.")

    # Get dependencies and blocks relations
    for bug in bugResult:
        rel = dict()
        rel["blocks"] = bugResult[bug].pop("blocks")
        rel["depends_on"] = bugResult[bug].pop("depends_on")
        relationResult[bug] = rel

    # Store the relations url
    urlResult[utils.KEY_ITEMS_RELATIONS] = result.url

    # Get attachments of bugs
    c = 0
    missedCreator = set()
    result = scratchBugListAttachments(conf, bugResult.keys()[:100])
    if result.ok:
        restResult = result.json()
        num = len(restResult["bugs"])
        for bug in restResult["bugs"]:
            # Get only bugs with attachments
            if not restResult["bugs"][bug] == []:
                attachmentResult[bug] = restResult["bugs"][bug]

                # For each attachments, get informations on creator and count the positive reviews
                for att in attachmentResult[bug]:
                    if not att["creator"] in devResult:
                        missedCreator.add(utils.encodeURIWithUTF8(att["creator"]))
                    
                    positive_reviews = 0
                    for flag in att["flags"]:
                        if flag["status"] == "+":
                            positive_reviews = positive_reviews + 1
                            
                    att["positive_reviews"] = positive_reviews
                c = c + len(attachmentResult[bug])

        r = scratchDeveloperList(conf, missedCreator)
        if r.ok:
            creatorResult = r.json()
            for creator in creatorResult["users"]:
                devResult[creator["name"]] = creator
        else:
            log.info("Attachments missed creators: connection error.")
                            
        log.info(str("Attachments: {}. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}. Creators added: {}").format(
            c,num,num-len(attachmentResult),len(attachmentResult),len(result.content), len(missedCreator)))
    else:
        log.info(str("Attachments: connection error. {}").format(r.query))

    # Store the attachments url
    urlResult[utils.KEY_ITEMS_ATTACHMENTS] = result.url

    # Get comments of bugs
    c = 0
    result = scratchBugListComments(conf, bugResult.keys()[:200])
    if result.ok:
        restResult = result.json()
        num = len(restResult["bugs"])
        for bug in restResult["bugs"]:
            # Get only bugs with comments
            if not restResult["bugs"][bug]["comments"] == []:
                commentResult[bug] = restResult["bugs"][bug]["comments"]
                c = c + len(commentResult[bug])

        log.info(str("Comments: {}. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}.").format(c,num,num-len(commentResult),len(commentResult),len(result.content)))
    else:
        log.info("Comments: connection error.")

    # Store the comments url
    urlResult[utils.KEY_ITEMS_COMMENTS] = result.url

    # Get history of bugs
    result = scratchBugListHistory(conf, bugResult.keys()[:200])
    if result.ok:
        restResult = result.json()
        num = len(restResult["bugs"])
        for bug in restResult["bugs"]:
            # Get only bugs with a not empty history
            if not bug["history"] == []:
                historyResult[bug["id"]] = bug
        
        log.info(str("History entries. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}.").format(num,num-len(historyResult),len(historyResult),len(result.content)))
    else:
        log.info("History: connection error.")

    # Store the history url
    urlResult[utils.KEY_ITEMS_HISTORY] = result.url

    issueAnalyzer.urlResult = urlResult
    issueAnalyzer.bugResult = bugResult
    issueAnalyzer.devResult = devResult
    issueAnalyzer.attachmentResult = attachmentResult
    issueAnalyzer.commentResult = commentResult
    issueAnalyzer.historyResult = historyResult
    issueAnalyzer.relationResult = relationResult

    log.info("Scratching is terminated.")

def analyze(issueAnalyzer):
    """Function to analyze the given data

    Get the project configuration, the dictionaries,
    analyze them and then store the result on database.

    Args:
       issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle

    Returns None: The result is stored on database

    """
    log.info("Issue analyzer is analyzing stored issues on cache.")

    bugResult = issueAnalyzer.bugResult
    devResult = issueAnalyzer.devResult
    attachmentResult = issueAnalyzer.attachmentResult
    commentResult = issueAnalyzer.commentResult
    historyResult = issueAnalyzer.historyResult
    relationResult = issueAnalyzer.relationResult

    conf = issueAnalyzer.conf
    dbm = DBManager(conf)
    projectId = dbm.get_issue_project(conf['issueAnalyzerURL'], conf['issueAnalyzerProjectName'],
                                      conf['issueAnalyzerPriority1'], conf['issueAnalyzerPriority2'], True)

    # Create the default developer
    issue_developer = list()
    issue_developer.append(("nobody@mozilla.org",
                            projectId,
                            "1",
                            "Nobody; OK to take it and work on it"))
    dbm.add_issue_developer(issue_developer)

    # Import developers on database
    for dev in devResult:
        # Parse the developers details
        issue_developer = list()

        # Don't import the default developer. It's already in database
        if not dev == "nobody@mozilla.org":
            issue_developer.append((dev,
                                    projectId,
                                    devResult[dev]["id"],
                                    utils.encodeWithUTF8(devResult[dev]["real_name"])))

        dbm.add_issue_developer(issue_developer)
    log.info(str("Imported {} developers on database.").format(len(devResult)))

    # Import bugs on database
    issue_data = list()
    issue_cclist = list()
    for bug in bugResult:
        # Parse the issue data
        priorityValue = 2
        if bugResult[bug]["priority"] == conf['issueAnalyzerPriority1']:
            priorityValue = 1

        severityValue = 7
        if bugResult[bug]["severity"] == conf['issueAnalyzerSeverity1']:
            severityValue = 1
        elif  bugResult[bug]["severity"] == conf['issueAnalyzerSeverity2']:
            severityValue = 2
        elif  bugResult[bug]["severity"] == conf['issueAnalyzerSeverity3']:
            severityValue = 3
        elif  bugResult[bug]["severity"] == conf['issueAnalyzerSeverity4']:
            severityValue = 4
        elif  bugResult[bug]["severity"] == conf['issueAnalyzerSeverity5']:
            severityValue = 5
        elif  bugResult[bug]["severity"] == conf['issueAnalyzerSeverity6']:
            severityValue = 6

        spentTime = None
        if bugResult[bug]["cf_last_resolved"] is not None:
            spentTime = utils.convertToDateTime(bugResult[bug]["cf_last_resolved"]) - utils.convertToDateTime(bugResult[bug]["creation_time"])
            spentTime = spentTime.days * 24 * 60 + spentTime.seconds / 60 # Time in minutes
        else:
            spentTime = datetime.now() - utils.convertToDateTime(bugResult[bug]["creation_time"])
            spentTime = spentTime.days * 24 * 60 + spentTime.seconds / 60 # Time in minutes

        issue_data.append((bug,
                           projectId,
                           utils.encodeWithUTF8(bugResult[bug]["summary"]),
                           bugResult[bug]["component"],
                           utils.convertToDateTime(bugResult[bug]["creation_time"]),
                           bugResult[bug]["creator"],
                           bugResult[bug]["assigned_to"],
                           spentTime,
                           bugResult[bug]["priority"],
                           priorityValue,
                           bugResult[bug]["severity"],
                           severityValue,
                           bugResult[bug]["status"],
                           bugResult[bug]["resolution"],
                           bugResult[bug]["is_open"],
                           bugResult[bug]["votes"],
                           bugResult[bug]["comment_count"],
                           utils.encodeWithUTF8(",".join(bugResult[bug]["keywords"])),
                           utils.convertToDateTime(bugResult[bug]["cf_last_resolved"])))        

        for cc in bugResult[bug]["cc"]:
            # Parse the CC list
            issue_cclist.append((bug,
                                 projectId,
                                 cc))

    dbm.add_issue_data(issue_data)
    dbm.add_issue_cclist(issue_cclist)
    
    log.info(str("Imported {} bugs and their cc lists on database.").format(len(bugResult)))

    # Import bug relations on database
    c = 0
    issue_dependencies = list()
    for bug in relationResult:
        blocks = relationResult[bug]["blocks"]
        dependencies = relationResult[bug]["depends_on"]
        c = c + len(blocks) + len(dependencies)
        
        for block in blocks:
            # Parse the blocked bug
            issue_dependencies.append((bug,
                                       projectId,
                                       block,
                                       "blocks"))

        for dependency in dependencies:
            # Parse the blocking bug
            issue_dependencies.append((bug,
                                       projectId,
                                       dependency,
                                       "depends on"))

    dbm.add_issue_dependencies(issue_dependencies)
    log.info(str("Imported {} relations of {} bugs.").format(c, len(relationResult)))

    # Import attachments on database
    c = 0
    issue_attachment = list()
    for bug in attachmentResult:
        c = c + len(attachmentResult[bug])
        for att in attachmentResult[bug]:
            # Parse the attachments details
            issue_attachment.append((att["id"],
                                     projectId,
                                     bug,
                                     att["creator"],
                                     utils.convertToDateTime(att["creation_time"]),
                                     att["is_obsolete"],
                                     att["is_patch"],
                                     att["is_private"],
                                     att["size"],
                                     att["positive_reviews"]))

    dbm.add_issue_attachment(issue_attachment)
    log.info(str("Imported {} attachments of {} bugs.").format(c, len(attachmentResult)))

    # Import comments on database
    c = 0
    issue_comment = list()  
    for bug in commentResult:
        c = c + len(commentResult[bug])
        for com in commentResult[bug]:
            # Parse the comment details
            issue_comment.append((com["id"],
                                  projectId,
                                  bug,
                                  com["author"],
                                  utils.convertToDateTime(com["creation_time"]),
                                  utils.encodeWithUTF8(com["raw_text"])))

    dbm.add_issue_comment(issue_comment)
    log.info(str("Imported {} comments of {} bugs.").format(c, len(commentResult)))

    # Import history on database
    c = 0
    issue_history = list()
    for bug in historyResult:
        history = historyResult[bug]["history"]
        for hist in history:
            for change in hist["changes"]:
                # Parse the history details
                c = c + 1
                attId = None
                if "attachment_id" in change.keys():
                    attId = change["attachment_id"]

                issue_history.append((bug,
                                      projectId,
                                      hist["who"],
                                      utils.convertToDateTime(hist["when"]),
                                      change["added"][:255],
                                      change["removed"][:255],
                                      attId,
                                      change["field_name"]))

    dbm.add_issue_history(issue_history)
    log.info(str("Imported {} history of {} bugs.").format(c, len(historyResult)))
    
    log.info("Import is terminated.")

    return projectId

def getResult(issueAnalyzer, projectId):
    """Function to calculate the result of developer-issue assignments

    Get the aggregated data from database's views, make the
    developer-issue assignments and store the result on database.

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle
        projectId (int): The id of the current project

    Returns None: The result is stored on database

    """
    conf = issueAnalyzer.conf
    dbm = DBManager(conf)

    # Get all the bug statistics
    bugStatistics = dict()
    result = dbm.get_view_assignment(projectId, utils.QUERY_TYPE_ASSIGNMENTS_STATS)
    row = result.fetchone()
    while row is not None:
        bugId = row[BUG_ID]
        component = row[COMPONENT]
        priority = row[STATS_PRIORITY]
        severity = row[STATS_SEVERITY]
        avgNumAssigned = row[AVG_NUM_ASSIGNED]
        avgDevAvgTime = row[AVG_DEV_AVG_TIME]
        avgNumComment = row[AVG_NUM_COMMENT]
        avgNumAttachment = row[AVG_NUM_ATTACHMENT]
        avgReviews = row[AVG_REVIEWS]
        avgSizeAttachment = row[AVG_SIZE_ATTACHMENT]

        bugStatistics[bugId] = {"component": component, "priority": priority, "severity": severity,
                                "avgNumAssigned": avgNumAssigned, "avgDevAvgTime": avgDevAvgTime, "avgNumComment": avgNumComment,
                                "avgNumAttachment": avgNumAttachment, "avgReviews": avgReviews, "avgSizeAttachment": avgSizeAttachment}
        
        row = result.fetchone()
    
    # Get all the bugs and their possible developers
    bugAssignments = dict()
    developers = dict()
    result = dbm.get_view_assignment(projectId, utils.QUERY_TYPE_ALL_ASSIGNMENTS)
    nAssignmentResult = result.rowcount
    row = result.fetchone()
    while row is not None:        
        bugId = row[BUG_ID]
        component = row[COMPONENT]
        priority = row[PRIORITY]
        severity = row[SEVERITY]
        developer = row[DEVELOPER]
        isOpen = row[IS_OPEN]
        reviews = row[REVIEWS]
        numAssigned = row[NUM_ASSIGNED]
        numAttachment = row[NUM_ATTACHMENT]
        numComment = row[NUM_COMMENT]
        sizeAttachment = row[SIZE_ATTACHMENT]
        devAvgTime = row[DEV_AVG_TIME]
        bugAvgETA = row[BUG_AVG_ETA]
        
        if not bugId in bugAssignments.keys():
            # First entry on bug
            bugAssignments[bugId] = [{"component": component, "priority": priority, "developer": developer, "isOpen": isOpen}]
        else:
            # Get the developers associated to the bug
            bugAssignments[bugId].append({"component": component, "priority": priority, "developer": developer, "isOpen": isOpen})

        developers[str("{}{}{}{}").format(developer, component, priority, isOpen)]= {"reviews": reviews,"numAssigned": numAssigned,
                                                                                     "numAttachment": numAttachment, "numComment": numComment,
                                                                                     "sizeAttachment": sizeAttachment, "devAvgTime": devAvgTime,
                                                                                     "bugAvgETA": bugAvgETA}

        row = result.fetchone()

    # Get all the bugs and their possible developers
    assignmentResults = dict()
    issue_assignment = list()
    developerTimeAssignments = dict()
    for bug in bugAssignments.keys():
        # Initialize the assignee variables
        assignee = None
        assigneeRank = -255
        assigneeNumAssigned = -255

        analysedDevelopers = list()
        stat = bugStatistics[bug]
        for dev in bugAssignments[bug]:
            # Don't analyze a developer twice
            if dev in analysedDevelopers:
                continue

            analysedDevelopers.append(dev)

            # Get the developer data
            developer = dev["developer"]
            component = dev["component"]
            priority = dev["priority"]

            # Get the developers details for the fixed bugs assigned
            devKey = str("{}{}{}0").format(developer, component, priority)
            result = utils.safeGetDeveloper(developers, devKey, ["reviews", "numAssigned", "numAttachment", "numComment", "sizeAttachment", "devAvgTime", "bugAvgETA"])
            devDetails = result[0]
            reviewsFixed = devDetails["reviews"]
            numAssignedFixed = devDetails["numAssigned"]
            numAttachmentFixed = devDetails["numAttachment"]
            numCommentFixed = devDetails["numComment"]
            sizeAttachmentFixed = devDetails["sizeAttachment"]
            devAvgTimeFixed = devDetails["devAvgTime"]
            bugAvgETAFixed = devDetails["bugAvgETA"]
            fixedBugsExists = result[1]

            # Get the developers details for the open bugs assigned                   
            devKey = str("{}{}{}1").format(developer, component, priority)
            result = utils.safeGetDeveloper(developers, devKey, ["reviews", "numAssigned", "numAttachment", "numComment", "sizeAttachment", "devAvgTime", "bugAvgETA"])
            devDetails = result[0]
            reviewsOpen = devDetails["reviews"]
            numAssignedOpen = devDetails["numAssigned"]
            numAttachmentOpen = devDetails["numAttachment"]
            numCommentOpen = devDetails["numComment"]
            sizeAttachmentOpen = devDetails["sizeAttachment"]
            devAvgTimeOpen = devDetails["devAvgTime"]
            bugAvgETAOpen = devDetails["bugAvgETA"]
            openBugsExists = result[1]

            # Get the complete developers details
            reviews = reviewsFixed + reviewsOpen
            numAssigned = numAssignedFixed + numAssignedOpen
            numAttachment = numAttachmentFixed + numAttachmentOpen
            numComment = numCommentFixed + numCommentOpen
            sizeAttachment = sizeAttachmentFixed + sizeAttachmentOpen
            devAvgTime = devAvgTimeFixed if fixedBugsExists else devAvgTimeOpen
            bugAvgETA = bugAvgETAFixed if fixedBugsExists else bugAvgETAOpen

            # Get the stats related to the bug
            avgReviews = stat["avgReviews"]
            avgNumAssigned = stat["avgNumAssigned"]
            avgNumAttachment = stat["avgNumAttachment"]
            avgNumComment = stat["avgNumComment"]
            avgSizeAttachment = stat["avgSizeAttachment"]
            avgDevAvgTime = stat["avgDevAvgTime"]

            # Get the stats related to the developer
            result = dbm.get_issue_developer_statistics(projectId, developer)
            statRow = result.fetchone()

            timeAvailable = statRow[0]
            timeUnavailable = statRow[1]
            
            timeAssignments = developerTimeAssignments[developer] if developer in developerTimeAssignments.keys() else 0
            developerBusy = (timeAvailable*conf["issueAnalyzerBugOpenedDays"]/conf["issueAnalyzerBugFixedDays"]-(timeUnavailable+timeAssignments)) > 0
            if not developerBusy == False:
                # avgNumAssigned/numAssigned
                availability = float(utils.safeDiv(avgNumAssigned, numAssigned, avgNumAssigned+1))

                # numAttachment/avgNumAttachment + numComment/avgNumComment
                collaborativity = float(utils.safeDiv(numAttachment, avgNumAttachment, numAttachment) + \
                                    utils.safeDiv(numComment, avgNumComment, numComment))

                # numAssigned/avgNumAssigned + reviews/avgReviews
                competency = float(utils.safeDiv(numAssigned, avgNumAssigned, numAssigned) + \
                                    utils.safeDiv(reviews, avgReviews, reviews))

                # avgDevAvgTime/devAvgTime + avgReviews/reviews*numAttachment/avgNumAttachment + sizeAttachment/avgSizeAttachment*devAvgTime/avgDevAvgTime
                reliability = float(utils.safeDiv(avgDevAvgTime, devAvgTime, avgDevAvgTime+1) + \
                                    utils.safeDiv(avgReviews, reviews, 0)*utils.safeDiv(numAttachment, avgNumAttachment, numAttachment) + \
                                    utils.safeDiv(sizeAttachment, avgSizeAttachment, sizeAttachment)/utils.safeDiv(devAvgTime, avgDevAvgTime, devAvgTime))                

                # Calculate the total rank
                rank = availability*0.2 + collaborativity*0.15 + competency*0.35 + reliability*0.2
                
                # If the rank is the best for this bug, assign it to the developer
                if rank > assigneeRank:
                    assignee = developer
                    assigneeRank = rank
                    
                    assigneeNumAssigned = numAssignedOpen+1
                    res = utils.safeSetDeveloper(developers, devKey, "numAssigned", assigneeNumAssigned,
                                                    ["reviews", "numAssigned", "numAttachment", "numComment", "sizeAttachment", "devAvgTime", "bugAvgETA"])

                    timeAssignments = timeAssignments+bugAvgETA
                    developerTimeAssignments[developer] = timeAssignments

        # Store the assignee if he/she exists
        if not assignee is None:
            assignmentResults[bug] = {"developer": assignee, "rank": assigneeRank, "assigned": assigneeNumAssigned}
            issue_assignment.append((bug, projectId, assignee))

    # Store the assignees on database
    dbm.add_issue_assignment(issue_assignment)
    log.info(str("Bug assigned: {} of {}. Possible assignments: {}.").format(len(assignmentResults), len(bugStatistics), nAssignmentResult))

    log.info("Analysis is terminated.")

def scratchBugOpenNotAssigned(conf):
    query = getQueryParams(conf, QUERY_BUG_OPEN_NOT_ASSIGNED)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_OPEN_NOT_ASSIGNED: {}".format(query)))

    return r

def scratchBugClosedFixed(conf):
    query = getQueryParams(conf, QUERY_BUG_CLOSED_FIXED)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_CLOSED_FIXED: {}".format(query)))

    return r

def scratchBugAssigned(conf):
    query = getQueryParams(conf, QUERY_BUG_ASSIGNED)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_ASSIGNED: {}".format(query)))

    return r

def scratchAttachment(conf, attachmentId):
    query = getQueryParams(conf, QUERY_ATTACHMENT_FROM_ID, attachmentId)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_ATTACHMENT_FROM_ID: {}".format(query)))

    return r

def scratchBugListAttachments(conf, attachmentId):
    query = getQueryParams(conf, QUERY_ATTACHMENT_OF_BUGLIST, attachmentId)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_ATTACHMENT_OF_BUGLIST: {}".format(query)))

    return r

def scratchBug(conf, bugId):
    query = getQueryParams(conf, QUERY_BUG_FROM_ID, bugId)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_FROM_ID: {}".format(query)))

    return r

def scratchDeveloper(conf, developerEmail):
    query = getQueryParams(conf, QUERY_DEVELOPER_FROM_EMAIL, developerEmail)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_DEVELOPER_FROM_EMAIL: {}".format(query)))

    return r

def scratchDeveloperList(conf, developerEmailList):
    query = getQueryParams(conf, QUERY_DEVELOPER_FROM_EMAIL_LIST, developerEmailList)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_DEVELOPER_FROM_EMAIL_LIST: {}".format(query)))

    return r

def scratchBugComments(conf, bugId):
    query = getQueryParams(conf, QUERY_COMMENT_OF_BUG, bugId)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_COMMENT_OF_BUG: {}".format(query)))

    return r

def scratchBugListComments(conf, bugIdOrList):
    query = getQueryParams(conf, QUERY_COMMENT_OF_BUGLIST, bugIdOrList)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_COMMENT_OF_BUGLIST: {}".format(query)))

    return r

def scratchBugHistory(conf, bugId):
    query = getQueryParams(conf, QUERY_HISTORY_OF_BUG, bugId)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_HISTORY_OF_BUG: {}".format(query)))

    return r

def scratchBugListHistory(conf, bugIdOrList):
    query = getQueryParams(conf, QUERY_HISTORY_OF_BUGLIST, bugIdOrList)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_HISTORY_OF_BUGLIST: {}".format(query)))

    return r

def scratchBugList(conf, bugId, bugStatus = {}):
    query = getQueryParams(conf, QUERY_BUG_FROM_LIST, bugId, bugStatus)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_FROM_LIST: {}".format(query)))

    return r

def scratchBugIdOrList(conf, bugIdOrList, bugStatus = {}):
    query = getQueryParams(conf, QUERY_BUG_FROM_ID_OR_LIST, bugIdOrList, bugStatus)

    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_FROM_ID_OR_LIST: {}".format(query)))

    return r

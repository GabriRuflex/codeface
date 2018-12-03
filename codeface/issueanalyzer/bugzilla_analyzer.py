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
Bugzilla IssueAnalyzer module
"""

import random
import time

from datetime import datetime
from logging import getLogger; log = getLogger(__name__)

import codeface.issueanalyzer.common_utils as utils
import codeface.issueanalyzer.bugzilla_analyzer_functions as functions

from codeface.configuration import Configuration
from codeface.dbmanager import DBManager
from codeface.util import BatchJobPool

SHOW_DEBUG = 0
MORE_DEVELOPERS = 0

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

def scratch(issueAnalyzer):
    """Function to scratch the bugtracker and get data

    Get the project configuration, query the bugtracker
    and then update the given dicts.

    Args:
       issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to update

    Returns None

    """
    log.info("IssueAnalyzer is scratching via Bugzilla module.")
    restResult = dict()

    urlResult = dict()
    bugResult = dict()
    devResult = dict()
    attachmentResult = dict()
    commentResult = dict()
    historyResult = dict()
    relationResult = dict()

    conf = issueAnalyzer.conf
    runMode = issueAnalyzer.runMode

    # Get and append all assigned open bugs
    result = functions.scratchBugOpenAssigned(conf)
    if result.ok:
        restResult = result.json()

        log.info(str("Bug assigned and open. Bugs: {}. Byte: {}.").format(len(result.json()["bugs"]),len(result.content)))
    else:
        log.info("Bug assigned and open: connection error.")

    if runMode == utils.RUN_MODE_TEST:
        # Set all open and assigned bug as unassigned
        numBugs = len(restResult["bugs"])
        for i in range(0, numBugs):
            # Get the bug
            bug = restResult["bugs"][i]

            # Save the real assignee
            bug["realassignee"] = bug["assigned_to_detail"]["name"]

            # Unassign the bug
            bug["assigned_to"] = "nobody@mozilla.org"
            bug["assigned_to_detail"] = {"email" : "nobody@mozilla.org", "id" : 1, "name" : "nobody@mozilla.org",
                                         "real_name" : "Nobody; OK to take it and work on it"}

    # Get and append all assigned fixed bugs
    previousPeriod = runMode == utils.RUN_MODE_TEST
    result = functions.scratchBugClosedFixed(conf, previousPeriod)
    if result.ok:
        restResult["bugs"] = restResult["bugs"] + result.json()["bugs"]

        log.info(str("Bug assigned and fixed. Bugs: {}. Byte: {}.").format(len(result.json()["bugs"]),len(result.content)))
    else:
        log.info("Bug assigned and fixed: connection error.")

    # Store the developers url
    urlResult[utils.KEY_ITEMS_DEVELOPERS] = utils.getUrlByRunMode(result.url, runMode)

    # Get all open bugs not assigned
    result = functions.scratchBugOpenNotAssigned(conf)
    if result.ok:
        restResult["bugs"] = restResult["bugs"] + result.json()["bugs"]

        log.info(str("Bug not assigned and open. Bugs: {}. Byte: {}.").format(len(result.json()["bugs"]),len(result.content)))
    else:
        log.info("Bug not assigned and open: connection error.")

    # Store the bugs url
    urlResult[utils.KEY_ITEMS_BUGS] = utils.getUrlByRunMode(result.url, runMode)

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
    result = functions.scratchBugIdOrList(conf, deps, bugStatus = 1)
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

        log.info(str("Dependencies. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}.").format(num,c,num-c,len(result.content)))
    else:
        log.info("Dependencies: connection error.")

    # Show total bug number
    log.info(str("Total number of analysed bug: {}").format(len(bugResult.keys())))

    # Get dependencies and blocks relations
    for bug in bugResult:
        rel = dict()
        rel["blocks"] = bugResult[bug].pop("blocks")
        rel["depends_on"] = bugResult[bug].pop("depends_on")
        relationResult[bug] = rel

    # Store the relations url
    urlResult[utils.KEY_ITEMS_RELATIONS] = utils.getUrlByRunMode(result.url, runMode)

    # Set queries limits
    maxBugs = 200
    numBugs = len(bugResult.keys())
    rangeBugs = (numBugs/maxBugs) + 1

    # Get attachments of bugs
    missedCreator = set()

    # Attachments counter total
    ct = 0
    # Attachments deleted counter total
    dt = 0

    for n in range(rangeBugs):
        f = (n+1)*maxBugs if (n+1)*maxBugs<numBugs else numBugs
        i = n*maxBugs
        result = functions.scratchBugListAttachments(conf, bugResult.keys()[i:f])
        if result.ok:
            restResult = result.json()
            num = len(restResult["bugs"])
            c = 0
            d = 0
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
                else:
                    d = d + 1
            log.info(str("Attachments ({}/{}): {}. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}.").format(
                n+1,rangeBugs,c,num,d,num-d,len(result.content)))

            # Update total counters
            ct = ct + c
            dt = dt + d

            # Wait 5 seconds to run the other queries
            time.sleep(5)
        else:
            log.info("Attachments: connection error.")


    r = functions.scratchDeveloperList(conf, missedCreator)
    if r.ok:
        creatorResult = r.json()
        for creator in creatorResult["users"]:
            devResult[creator["name"]] = creator
    else:
        log.info("Attachments missed creators: connection error.")
                        
    log.info(str("Attachments: {}. Bugs: {}. Deleted: {}. Remains: {}. Creators added: {}.").format(
        ct,numBugs,dt,len(attachmentResult), len(missedCreator)))

    # Store the attachments url
    urlResult[utils.KEY_ITEMS_ATTACHMENTS] = utils.getUrlByRunMode(result.url, runMode)

    # Get comments of bugs

    # Comments counter total
    ct = 0
    # Comments deleted counter total
    dt = 0

    for n in range(rangeBugs):
        f = (n+1)*maxBugs if (n+1)*maxBugs<numBugs else numBugs
        i = n*maxBugs
        result = functions.scratchBugListComments(conf, bugResult.keys()[i:f])
        if result.ok:
            restResult = result.json()
            num = len(restResult["bugs"])
            c = 0
            d = 0
            for bug in restResult["bugs"]:
                # Get only bugs with comments
                if not restResult["bugs"][bug]["comments"] == []:
                    commentResult[bug] = restResult["bugs"][bug]["comments"]
                    c = c + len(commentResult[bug])
                else:
                    d = d + 1

            log.info(str("Comments ({}/{}): {}. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}.").format(
                n+1,rangeBugs,c,num,d,num-d,len(result.content)))

            # Update total counters
            ct = ct + c
            dt = dt + d

            # Wait 5 seconds to run the other queries
            time.sleep(5)
        else:
            log.info("Comments: connection error.")

    log.info(str("Comments: {}. Bugs: {}. Deleted: {}. Remains: {}.").format(
        ct,numBugs,dt,len(commentResult)))

    # Store the comments url
    urlResult[utils.KEY_ITEMS_COMMENTS] = utils.getUrlByRunMode(result.url, runMode)

    # Get history of bugs

    # History counter total
    ct = 0
    # History deleted counter total
    dt = 0

    for n in range(rangeBugs):
        f = (n+1)*maxBugs if (n+1)*maxBugs<numBugs else numBugs
        i = n*maxBugs
        result = functions.scratchBugListHistory(conf, bugResult.keys()[i:f])
        if result.ok:
            restResult = result.json()
            num = len(restResult["bugs"])
            c = 0
            d = 0
            for bug in restResult["bugs"]:
                # Get only bugs with a not empty history
                if not bug["history"] == []:
                    historyResult[bug["id"]] = bug
                    c = c + 1
                else:
                    d = d + 1

            log.info(str("History entries ({}/{}): {}. Bugs: {}. Deleted: {}. Remains: {}. Byte: {}.").format(
                n+1,rangeBugs,c,num,d,num-d,len(result.content)))

            # Update total counters
            ct = ct + c
            dt = dt + d

            # Wait 5 seconds to run the other queries
            time.sleep(5)
        else:
            log.info("History: connection error.")

    log.info(str("History entries: {}. Bugs: {}. Deleted: {}. Remains: {}.").format(
        ct,numBugs,dt,len(historyResult)))

    # Store the history url
    urlResult[utils.KEY_ITEMS_HISTORY] = utils.getUrlByRunMode(result.url, runMode)

    issueAnalyzer.urlResult = urlResult
    issueAnalyzer.bugResult = bugResult
    issueAnalyzer.devResult = devResult
    issueAnalyzer.attachmentResult = attachmentResult
    issueAnalyzer.commentResult = commentResult
    issueAnalyzer.historyResult = historyResult
    issueAnalyzer.relationResult = relationResult

    log.info("Scratching is terminated.")

def analyzeAndImport(issueAnalyzer):
    """Function to analyze and import on the database the given data

    Get the project configuration, the dictionaries,
    analyze them and then store the result on database.

    Args:
       issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to handle

    Returns None: The result is stored on database.

    """
    analysisMode = "analysis" if issueAnalyzer.runMode == utils.RUN_MODE_ANALYSIS else "test"
    log.info(str("IssueAnalyzer is analyzing stored issues on cache in {} mode.").format(analysisMode))

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
        priorityValue = 6
        if bugResult[bug]["priority"] == conf['issueAnalyzerPriority1']:
            priorityValue = 1
        if bugResult[bug]["priority"] == conf['issueAnalyzerPriority2']:
            priorityValue = 2
        if bugResult[bug]["priority"] == conf['issueAnalyzerPriority3']:
            priorityValue = 3
        if bugResult[bug]["priority"] == conf['issueAnalyzerPriority4']:
            priorityValue = 4
        if bugResult[bug]["priority"] == conf['issueAnalyzerPriority5']:
            priorityValue = 5

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

        spentTime = 0
        if bugResult[bug]["assigned_to"] <> "nobody@mozilla.org":
            if bugResult[bug]["cf_last_resolved"] is not None:
                spentTime = utils.convertToDateTime(bugResult[bug]["cf_last_resolved"]) - utils.convertToDateTime(bugResult[bug]["creation_time"])
                spentTime = spentTime.days * 24 * 60 + spentTime.seconds / 60 # Time in minutes
            else:
                spentTime = datetime.now() - utils.convertToDateTime(bugResult[bug]["creation_time"])
                spentTime = spentTime.days * 24 * 60 + spentTime.seconds / 60 # Time in minutes

        realAssignee = "NULL"
        if "realassignee" in bugResult[bug].keys():
            realAssignee = bugResult[bug]["realassignee"]

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
                           utils.convertToDateTime(bugResult[bug]["cf_last_resolved"]),
                           realAssignee))

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

def handleResult(issueAnalyzer, projectId):
    """Function to handle the result of developer-issue assignments

    Get the project's configuration and call, if necessary, the grid search routines.

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to handle
        projectId (int): The id of the current project

    Returns None: The result is handled, the score is calculated and printed.

    """
    import codeface.issueanalyzer.gridtest as gridtest

    conf = issueAnalyzer.conf
    dbm = DBManager(conf)

    timeIncrement = conf["issueAnalyzerTimeIncrement"]
    coeffAvailability = conf["issueAnalyzerAvailability"]
    coeffCollaborativity = conf["issueAnalyzerCollaborativity"]
    coeffCompetency = conf["issueAnalyzerCompetency"]
    coeffProductivity = conf["issueAnalyzerProductivity"]
    coeffReliability = conf["issueAnalyzerReliability"]

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
    nPA = result.rowcount
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

    # Get the results
    issue_assignment = getResult(issueAnalyzer, projectId, bugAssignments, bugStatistics, developers)

    # Get score
    (nA, tA, tP, fP, fN, P, R, F) = getScore(issueAnalyzer, projectId, bugStatistics, issue_assignment)

    # Print the result
    printResult(issueAnalyzer, nA, tA, nPA, tP, fP, fN, P, R, F)

    # If runMode is TEST, make also a grid search to optimize qualities
    if issueAnalyzer.runMode == utils.RUN_MODE_TEST:
        # Create parameters to test
        gridSearchParameters = {"coeffAvailability": [i for i in range(0, 2)], #2
                                "coeffCollaborativity": [i for i in range(0, 2)], #4
                                "coeffCompetency": [i for i in range(0, 2)], #5
                                "coeffProductivity": [i for i in range(0, 2)], #2
                                "coeffReliability": [i for i in range(0, 2)]} #6
        gridSearchList = generateCoefficientList(gridSearchParameters)

        bestScore = 0
        bestCoefficients = {"coeffAvailability": 0, "coeffCollaborativity": 0,
                            "coeffCompetency": 0, "coeffProductivity": 0, "coeffReliability": 0}
        
        # Search best score
        log.info("Looking for the best coefficients to use...")
        while bool(gridSearchList):
            # Get new coefficients
            coefficients = gridSearchList.pop()
            # Get score for current coefficients
            score = calculateScore(issueAnalyzer, projectId, bugAssignments, bugStatistics, developers, coefficients)

            # Check best score
            if score > bestScore:
                bestScore = score
                bestCoefficients = coefficients

        log.info(str("Best score (FMeasure): {} with coeffAvailability: {}, coeffCollaborativity: {}, " \
                     "coeffCompetency: {}, coeffProductivity: {} coeffReliability: {}.").format(
                         round(bestScore,2), bestCoefficients["coeffAvailability"], bestCoefficients["coeffCollaborativity"],
                         bestCoefficients["coeffCompetency"], bestCoefficients["coeffProductivity"], bestCoefficients["coeffReliability"]))

    log.info("Analysis is terminated.")

def getResult(issueAnalyzer, projectId, bugAssignments, bugStatistics, developers, differentCoeff = {}):
    """Function to calculate the result of developer-issue assignments

    Get the aggregated data from database's views, make the
    developer-issue assignments and store the result on database.

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to handle
        projectId (int): The id of the current project
        bugAssignments (dict): a dict that contains a set of possible assignments
        bugStatistics (dict) : a dict that contains a set of bug's statistics
        developers (dict)    : a dict that contains developers' data
        differentCoeff (dict): a dict that contains a set of coefficients

    Returns None: The result is stored on database

    """
    conf = issueAnalyzer.conf
    dbm = DBManager(conf)

    timeIncrement = conf["issueAnalyzerTimeIncrement"]
    coeffAvailability = conf["issueAnalyzerAvailability"]
    coeffCollaborativity = conf["issueAnalyzerCollaborativity"]
    coeffCompetency = conf["issueAnalyzerCompetency"]
    coeffProductivity = conf["issueAnalyzerProductivity"]
    coeffReliability = conf["issueAnalyzerReliability"]

    # Overwrite coefficients if needed
    if differentCoeff <> {}:
        coeffAvailability = differentCoeff["coeffAvailability"]
        coeffCollaborativity = differentCoeff["coeffCollaborativity"]
        coeffCompetency = differentCoeff["coeffCompetency"]
        coeffProductivity = differentCoeff["coeffProductivity"]
        coeffReliability = differentCoeff["coeffReliability"]

    # Get all the bugs and their possible developers
    assignmentResults = dict()
    issue_assignment = list()
    developerTimeAssignments = dict()
    developerBusyDict = dict()
    for bug in bugAssignments.keys():
        # Initialize the assignee variables
        assignee = None
        assigneeTime = 0
        assigneeRank = -255
        assigneeNumAssigned = -255

        analysedDevelopers = list()
        stat = bugStatistics[bug]
        for dev in bugAssignments[bug]:
            # Don't analyze developer without time
            if dev["developer"] in developerBusyDict.keys():
                continue

            # Don't analyze a developer twice for the same bug
            if dev["developer"] in analysedDevelopers:
                continue
            analysedDevelopers.append(dev["developer"])

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
            timeAvailable = dbm.get_issue_developer_statistics(projectId, developer, 0)
            timeUnavailable = dbm.get_issue_developer_statistics(projectId, developer, 1)
            
            timeAssignments = developerTimeAssignments[developer] if developer in developerTimeAssignments.keys() else 0
            #log.info(str("DEV: {} TIME ASSIGNMENTS: {}").format(developer, timeAssignments))
            developerBusy = timeIncrement*float(timeAvailable*conf["issueAnalyzerBugOpenedDays"]/conf["issueAnalyzerBugFixedDays"]) - \
                            float(timeUnavailable+timeAssignments) <= 0
            if not developerBusy:
                # avgNumAssigned/numAssigned
                availability = float(utils.safeDiv(avgNumAssigned, numAssigned, avgNumAssigned+1))

                # numAttachment/avgNumAttachment + numComment/avgNumComment
                collaborativity = float(utils.safeDiv(numAttachment, avgNumAttachment, numAttachment) + \
                                    utils.safeDiv(numComment, avgNumComment, numComment))

                # numAssigned/avgNumAssigned + reviews/avgReviews
                competency = float(utils.safeDiv(numAssigned, avgNumAssigned, numAssigned) + \
                                    utils.safeDiv(reviews, avgReviews, reviews))

                # (avgReviews/reviews*(sizeAttachment/avgSizeAttachment * avgNumAttachment/numAttachment) + numComment/avgNumComment) * avgDevAvgTime/devAvgTime
                productivity = float((utils.safeDiv(reviews, avgReviews, 0) * \
                                     (utils.safeDiv(sizeAttachment, avgSizeAttachment, sizeAttachment) * \
                                      utils.safeDiv(numAttachment, avgNumAttachment, numAttachment)) + \
                                      utils.safeDiv(numComment, avgNumComment, numComment)) * \
                                     utils.safeDiv(avgDevAvgTime, devAvgTime, avgDevAvgTime + 1))

                # numAssigned/avgNumAssigned * avgDevAvgTime/devAvgTime
                reliability = float(utils.safeDiv(numAssigned, avgNumAssigned, numAssigned) * \
                                    utils.safeDiv(avgDevAvgTime, devAvgTime, avgDevAvgTime + 1))               

                # Calculate the total rank
                rank = availability*coeffAvailability + collaborativity*coeffCollaborativity + competency*coeffCompetency + \
                       productivity*coeffProductivity + reliability*coeffReliability

                # If the rank is the best for this bug, assign it to the developer
                if rank > assigneeRank:
                    # Delete previous developer time assignments
                    if assignee <> None:
                        developerTimeAssignments[assignee] -= assigneeTime

                        # Remove developer to busy dict, if present
                        if assignee in developerBusyDict:
                            del developerBusyDict[assignee]
                    
                    if SHOW_DEBUG:
                        log.info(str("Bug {} assigned to {} with rank {} (Availability: {}, Collaborativity: {}, Competency: {}, Productivity: {}, Reliability: {})").format(
                            bug,dev["developer"],rank,availability,collaborativity,competency,productivity,reliability))

                    # Set new assignee
                    assignee = developer
                    assigneeRank = rank
                    
                    assigneeNumAssigned = numAssignedOpen+1
                    res = utils.safeSetDeveloper(developers, devKey, "numAssigned", assigneeNumAssigned,
                                                    ["reviews", "numAssigned", "numAttachment", "numComment", "sizeAttachment", "devAvgTime", "bugAvgETA"])

                    assigneeTime = devAvgTime
                    timeAssignments = timeAssignments+assigneeTime
                    developerTimeAssignments[developer] = timeAssignments
                elif SHOW_DEBUG:
                    log.info(str("Bug {} not assigned to {} with rank {} (Availability: {}, Collaborativity: {}, Competency: {}, Productivity: {}, Reliability: {})").format(
                        bug,dev["developer"],rank,availability,collaborativity,competency,productivity,reliability))
            else:
                # Add developer to busy dict
                developerBusyDict[developer] = True

        # Store the assignee if he/she exists
        if not assignee is None:
            assignmentResults[bug] = {"developer": assignee, "rank": assigneeRank, "assigned": assigneeNumAssigned}
            issue_assignment.append((bug, projectId, assignee))

    return issue_assignment

def getScore(issueAnalyzer, projectId, bugStatistics, issue_assignment):
    """Function to calculate the score of given result

    Get the project's data and calculate the score.

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to handle
        projectId (int)        : The id of the current project
        bugStatistics (dict)   : a dict that contains a set of bug's statistics
        issue_assignment (dict): a dict that contains the assignments

    Returns:
        nA  (int): number of assigned bugs
        tA  (int): total number to be assigned
        tP  (int): true positive value
        fP  (int): false positive value
        fN  (int): false negative value
        P   (int): Precision value
        R   (int): Recall value
        F   (int): FMeasure value
    """
    conf = issueAnalyzer.conf
    dbm = DBManager(conf)

    nA = len(issue_assignment)
    tA = len(bugStatistics)
    tP = 0
    fP = 0
    fN = 0
    P = 0
    R = 0
    F = 0

    # Store the assignees on database
    dbm.add_issue_assignment(issue_assignment)

    # If runMode is TEST, check the degree of compliance
    if issueAnalyzer.runMode == utils.RUN_MODE_TEST:
        realityCheckResult = dbm.get_view_reality_check(projectId)
        (tP, fP, fN)= realityCheckResult.fetchone()

        # Calculate the Precision, Recall and FMeasure values
        P = utils.safeDiv(tP, float(tP+fN), 0)
        R = utils.safeDiv(tP, float(tP+fP), 0)
        F = utils.safeDiv(2*P*R, P+R, 0)

    return (nA, tA, tP, fP, fN, P, R, F)

def printResult(issueAnalyzer, nA, tA, nPA, tP, fP, fN, P, R, F):
    """Function to print the result

    Get the project's data and print the result.

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to handle
        nA  (int): number of assigned bugs
        tA  (int): total number to be assigned
        tP  (int): true positive value
        fP  (int): false positive value
        fN  (int): false negative value
        P   (int): Precision value
        R   (int): Recall value
        F   (int): FMeasure value

    Returns None: The results are printed

    """
    log.info(str("Bug assigned: {} of {}. Possible assignments: {}.").format(nA, tA, nPA))

    # If runMode is TEST, check the degree of compliance
    if issueAnalyzer.runMode == utils.RUN_MODE_TEST:
        log.info(str("Reality check assignments values: TruePositive: {} - FalsePositive: {} - FalseNegative: {} - " \
                     "Precision: {} - Recall: {} - FMeasure: {}.").format(tP, fP, fN, round(P,2), round(R,2), round(F,2)))

def deleteProjectAssignments(issueAnalyzer, projectId):
    """Function to delete the project assignments

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to handle
        projectId (int): The id of the current project

    Returns: None
    """
    conf = issueAnalyzer.conf
    dbm = DBManager(conf)

    dbm.delete_issue_assignment(projectId)

def generateCoefficientList(gridSearchParameters):
    """Function to generate a list of coefficients

    It takes a dict and it converts the dict to a list.

    Args:
        gridSearchParameters (dict): a dictonary with the allowed coefficients

    Returns:
        coefficientList (list): a list of coefficients
    """
    # Create a new list
    coefficientList = list()
    # Calculate the coefficients and append to the list
    for a in gridSearchParameters["coeffAvailability"]:
        for b in gridSearchParameters["coeffCollaborativity"]:
            for c in gridSearchParameters["coeffCompetency"]:
                for d in gridSearchParameters["coeffProductivity"]:
                    for e in gridSearchParameters["coeffReliability"]:
                        coefficientList.append({"coeffAvailability": a, "coeffCollaborativity": b, "coeffCompetency": c,
                                                "coeffProductivity": d, "coeffReliability": e})
    return coefficientList

def calculateScore(issueAnalyzer, projectId, bugAssignments, bugStatistics, developers, coefficients):
    """Function to calculate the score of a set of assignments

    It takes a project, it deletes the current assignments, it makes a new one and it calculates the score of it.

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): IssueAnalyzer instance to handle
        projectId (int): The id of the current project
        bugAssignments (dict): a dict that contains a set of possible assignments
        bugStatistics (dict) : a dict that contains a set of bug's statistics
        developers (dict)    : a dict that contains developers' data
        coefficients (dict)  : a dict that contains the current coefficients

    Returns:
        F (float): score of assignment
    """
    # Call Bugzilla Analyzer routines
    deleteProjectAssignments(issueAnalyzer, projectId)
    issue_assignment = getResult(issueAnalyzer, projectId, bugAssignments, bugStatistics, developers, coefficients)
    (nA, tA, tP, fP, fN, P, R, F) = getScore(issueAnalyzer, projectId, bugStatistics, issue_assignment)

    # Return F=0 if we didn't assign all bugs
    if nA < tA:
        F = 0

    return F

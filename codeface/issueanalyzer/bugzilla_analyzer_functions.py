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
Bugzilla IssueAnalyzer module's functions
"""

import random
import requests
from datetime import datetime, timedelta
from logging import getLogger; log = getLogger(__name__)

SHOW_DEBUG = 0

# Definitions of query parameters
QUERY_BUG_OPEN_ASSIGNED = 0
QUERY_BUG_OPEN_NOT_ASSIGNED = 1
QUERY_BUG_CLOSED_FIXED = 2
QUERY_BUG_CLOSED_FIXED_PREVIOUS = 3
QUERY_ATTACHMENT_FROM_ID = 4
QUERY_ATTACHMENT_OF_BUGLIST = 5
QUERY_BUG_FROM_ID = 6
QUERY_DEVELOPER_FROM_EMAIL = 7
QUERY_DEVELOPER_FROM_EMAIL_LIST = 8
QUERY_COMMENT_OF_BUG = 9
QUERY_COMMENT_OF_BUGLIST = 10
QUERY_HISTORY_OF_BUG = 11
QUERY_HISTORY_OF_BUGLIST = 12
QUERY_BUG_FROM_LIST = 13
QUERY_BUG_FROM_ID_OR_LIST = 14

def getQueryParams(conf, queryType, idParam = [], bugStatus = []):
    """Function to build the REST query

    Get the project configuration the query type and all the
    specific query parameters, then creates and returns the query.

    Args:
        conf(codeface.configuration.Configuration): Path of the Codeface configuration file
        queryType(int): Path of the project configuration file
            QUERY_BUG_OPEN_ASSIGNED:
            QUERY_BUG_OPEN_NOT_ASSIGNED:
            QUERY_BUG_CLOSED_FIXED:
            QUERY_BUG_CLOSED_FIXED_PREVIOUS:
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
    if queryType == QUERY_BUG_OPEN_ASSIGNED:
        # Get bugs assigned in the last [x] days (used to get a list of active developers)
        date = (datetime.today() - timedelta(days=conf["issueAnalyzerBugOpenedDays"])).strftime("%Y-%m-%d")
        params = str("{}rest/bug?include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,creator,comment_count,depends_on,keywords,is_open,priority,resolution,severity,summary,status,votes" \
                     "&chfield=assigned_to&chfieldfrom={}&chfieldto=Now&f1=assigned_to&o1=notequals&v1=nobody%40mozilla.org" \
                     "&priority={}&priority={}&product={}&resolution=---").format(
                         conf['issueAnalyzerURL'], date, conf["issueAnalyzerPriority1"], conf["issueAnalyzerPriority2"], conf["issueAnalyzerProduct"])
    elif queryType == QUERY_BUG_OPEN_NOT_ASSIGNED:
        # Get bug opened and not assigned in the last [x] days
        date = (datetime.today() - timedelta(days=conf["issueAnalyzerBugOpenedDays"])).strftime("%Y-%m-%d")
        params = str("{}rest/bug?include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,creator,comment_count,depends_on,keywords,is_open,priority,resolution,severity,summary,status,votes" \
                     "&bug_status=NEW&bug_status=ASSIGNED&is_private=&chfield=[Bug creation]&chfieldfrom={}&chfieldto=Now" \
                     "&f1=assigned_to&o1=equals&v1=nobody%40mozilla.org&priority={}&priority={}&product={}&resolution=---").format(
                         conf['issueAnalyzerURL'], date, conf["issueAnalyzerPriority1"], conf["issueAnalyzerPriority2"], conf["issueAnalyzerProduct"])
    elif queryType == QUERY_BUG_CLOSED_FIXED:
        # Get bugs fixed and resolved in the last [x] days (used to get a list of active developers)
        date = (datetime.today() - timedelta(days=conf["issueAnalyzerBugFixedDays"])).strftime("%Y-%m-%d")
        params = str("{}rest/bug?include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,creator,comment_count,depends_on,keywords,is_open,priority,resolution,severity,summary,status,votes" \
                     "&chfield=resolution&chfieldfrom={}&chfieldto=Now&chfieldvalue=FIXED&f1=assigned_to&o1=notequals&v1=nobody%40mozilla.org" \
                     "&priority={}&priority={}&product={}&resolution=FIXED").format(
                         conf['issueAnalyzerURL'], date, conf["issueAnalyzerPriority1"], conf["issueAnalyzerPriority2"], conf["issueAnalyzerProduct"])
    elif queryType == QUERY_BUG_CLOSED_FIXED_PREVIOUS:
        # Get bugs fixed and resolved in the not last [x] days (used to get a list of bugs and developer for simulation)
        dateFrom = (datetime.today() - timedelta(days=conf["issueAnalyzerBugFixedDays"]+conf["issueAnalyzerBugOpenedDays"])).strftime("%Y-%m-%d")
        dateTo = (datetime.today() - timedelta(days=conf["issueAnalyzerBugOpenedDays"])).strftime("%Y-%m-%d")
        params = str("{}rest/bug?include_fields=id,assigned_to,blocks,cc,cf_last_resolved,component,creation_time,creator,comment_count,depends_on,keywords,is_open,priority,resolution,severity,summary,status,votes" \
                     "&chfield=resolution&chfieldfrom={}&chfieldto={}&chfieldvalue=FIXED&v1=nobody%40mozilla.org&f1=assigned_to&o1=notequals" \
                     "&priority={}&priority={}&product={}&resolution=FIXED").format(
                         conf['issueAnalyzerURL'], dateFrom, dateTo, conf["issueAnalyzerPriority1"], conf["issueAnalyzerPriority2"], conf["issueAnalyzerProduct"])
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

def scratchBugOpenAssigned(conf):
    query = getQueryParams(conf, QUERY_BUG_OPEN_ASSIGNED)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_OPEN_ASSIGNED: {}".format(query)))

    return r

def scratchBugOpenNotAssigned(conf):
    query = getQueryParams(conf, QUERY_BUG_OPEN_NOT_ASSIGNED)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        log.info(str("QUERY_BUG_OPEN_NOT_ASSIGNED: {}".format(query)))

    return r

def scratchBugClosedFixed(conf, previousPeriod):
    queryType = QUERY_BUG_CLOSED_FIXED
    if previousPeriod:
        queryType = QUERY_BUG_CLOSED_FIXED_PREVIOUS
    query = getQueryParams(conf, queryType)
    
    r = requests.get(query)
    if SHOW_DEBUG:
        if not previousPeriod:
            log.info(str("QUERY_BUG_CLOSED_FIXED: {}".format(query)))
        else:
            log.info(str("QUERY_BUG_CLOSED_FIXED_PREVIOUS: {}".format(query)))

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

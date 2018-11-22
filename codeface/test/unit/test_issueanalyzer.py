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
# Copyright 2014 by Siemens AG, Mitchell Joblin <mitchell.joblin.ext@siemens.com>
# All Rights Reserved. 

import os
import unittest
import tempfile
import datetime
import logging
from logging import getLogger; log = getLogger(__name__)

from shutil import rmtree
from tempfile import NamedTemporaryFile

import codeface.issueanalyzer.bugzilla_analyzer as bugzilla
import codeface.issueanalyzer.common_utils as utils
import codeface.issueanalyzer.issue_cache as cache

from codeface.configuration import Configuration
from codeface.dbmanager import DBManager
from codeface.logger import (set_log_level, start_logfile, stop_logfile)

from codeface.issueanalyzer.issueanalyzer_handler import IssueAnalyzer

TEST_RESULTS_ON_FILE = 1

class TestIssueAnalyzer(unittest.TestCase):
    '''Test issue analyzer functions'''

    @classmethod
    def setUpClass(self):
        '''
        Constructs a set of bug objects for testing purposes
        '''
        if TEST_RESULTS_ON_FILE:
            set_log_level("error")
            start_logfile("issueAnalyzer_test.log", "info")

        # Create temporary folder
        self.tmpDirectory = tempfile.mkdtemp()
        self.fakeDir = os.path.join(self.tmpDirectory, "fake/path")
        
        # Create a test configuration file
        self.global_conf = NamedTemporaryFile(delete=False)
        self.global_conf.write("""
            # Database access information
            dbhost: localhost
            dbuser: codeface
            dbpwd: codeface
            dbname: codeface
            # PersonService Settings
            idServicePort: 8080
            idServiceHostname: localhost
        """)
        self.global_conf.close()

        self.project_conf = NamedTemporaryFile(delete=False)
        self.project_conf.write("""
            project: theproject
            repo: therepo
            description: the description
            ml: the mailing list
            revisions: [ "v1", "v2"]
            rcs : ["v1rc0", "v2rc0"]
            tagging: tag

            issueAnalyzerProjectName: Bugzilla Core
            issueAnalyzerType: bugzilla

            issueAnalyzerURL: bugzilla.url
            issueAnalyzerProduct: Bugzilla Project

            issueAnalyzerTimeIncrement: 1.1
            issueAnalyzerAvailability: 0.2
            issueAnalyzerCollaborativity: 0.15
            issueAnalyzerCompetency: 0.15
            issueAnalyzerProductivity: 0.3
            issueAnalyzerReliability: 0.2

            issueAnalyzerBugOpenedDays: 60
            issueAnalyzerBugFixedDays: 90
            issueAnalyzerPriority1: P1
            issueAnalyzerPriority2: P2
            issueAnalyzerSeverity1: blocker
            issueAnalyzerSeverity2: critical
            issueAnalyzerSeverity3: major
            issueAnalyzerSeverity4: normal
            issueAnalyzerSeverity5: minor
            issueAnalyzerSeverity6: trivial
            issueAnalyzerSeverity7: enhancement
        """)
        self.project_conf.close()

        self.conf = Configuration.load(self.global_conf.name, self.project_conf.name)
        self.dbm = DBManager(self.conf)

        # Bugs
        self.bugResult = {1: {u'status': u'NEW', u'severity': u'normal', u'creator': u'mike@joe.url', u'cc': [u'john.smith@test.url'],
                     u'creator_detail': {u'id': 1, u'email': u'mike@joe.url', u'name': u'mike@joe.url',
                                         u'real_name': u'Mike Joe'},
                     u'creation_time': u'2018-08-13T00:36:22Z', u'votes': 0, u'id': 1,
                     u'cc_detail': [{u'id': 2, u'email': u'john.smith@test.url',u'name': u'john.smith@test.url', u'real_name': u'John Smith'}],
                     u'priority': u'P2', u'comment_count': 3, u'is_open': True, u'assigned_to': u'mike@joe.url', u'keywords': [u'key1', u'key2'], u'component': u'DOM: Networking',
                     u'summary': u'New bug.', u'resolution': u'', u'cf_last_resolved': None}}

        # Developers
        self.devResult = {u'mike@joe.url': {u'id': 1, u'name': u'mike@joe.url', u'real_name': u'Mike Joe'}}

        # Attachments
        self.attachmentResult = {1: [{u'creator': u'mike@joe.url', u'is_obsolete': 1, u'is_patch': 0, u'creation_time': u'2018-05-07T19:13:25Z', u'id': 1,
                               u'bug_id': 1, u'flags': [], 'positive_reviews': 0, u'last_change_time': u'2018-05-30T18:58:54Z', u'is_private': 0, u'size': 59}]}

        # Comments
        self.commentResult = {1: [{u'attachment_id': None, u'author': u'jimmy@test.url', u'creation_time': u'2018-05-01T21:59:30Z', u'bug_id': 1,
                           u'raw_text': u'It is a bug.',
                           u'id': 1}]}

        # History
        self.historyResult = {1: {u'alias': None, u'id': 1,
                         u'history': [{u'changes': [{u'removed': u'--', u'field_name': u'priority', u'added': u'P2'},
                                                    {u'removed': u'', u'field_name': u'cc', u'added': u'john.smith@test.url'},
                                                    {u'removed': u'nobody@mozilla.org', u'field_name': u'assigned_to', u'added': u'mike@joe.url'},
                                                    {u'removed': u'', u'field_name': u'whiteboard', u'added': u'[necko-triaged]'}],
                                       u'who': u'john.smith@test.url', u'when': u'2018-08-13T11:04:28Z'}]}}

        # Relations
        self.relationResult = {1: {'depends_on': [3], 'blocks': [2]}}
        
        self.urlResult = dict()
        self.urlResult[utils.KEY_ITEMS_BUGS] = "bugzilla.url/bugs"
        self.urlResult[utils.KEY_ITEMS_DEVELOPERS] = "bugzilla.url/developers"
        self.urlResult[utils.KEY_ITEMS_RELATIONS] = "bugzilla.url/relations"
        self.urlResult[utils.KEY_ITEMS_ATTACHMENTS] = "bugzilla.url/attachments"
        self.urlResult[utils.KEY_ITEMS_COMMENTS] = "bugzilla.url/comments"
        self.urlResult[utils.KEY_ITEMS_HISTORY] = "bugzilla.url/history"

        self.idxBugName = cache.get_path("/", self.urlResult[utils.KEY_ITEMS_BUGS])[1:]
        self.idxDevName = cache.get_path("/", self.urlResult[utils.KEY_ITEMS_DEVELOPERS])[1:]
        self.idxRelName = cache.get_path("/", self.urlResult[utils.KEY_ITEMS_RELATIONS])[1:]
        self.idxAtcName = cache.get_path("/", self.urlResult[utils.KEY_ITEMS_ATTACHMENTS])[1:]
        self.idxComName = cache.get_path("/", self.urlResult[utils.KEY_ITEMS_COMMENTS])[1:]
        self.idxHisName = cache.get_path("/", self.urlResult[utils.KEY_ITEMS_HISTORY])[1:]

        # Create an IssueAnalyzer's instance
        self.issueAnalyzer = IssueAnalyzer("analysisOnly", self.global_conf.name, self.project_conf.name, self.fakeDir)

        self.issueAnalyzer.urlResult = self.urlResult
        self.issueAnalyzer.bugResult = self.bugResult
        self.issueAnalyzer.devResult = self.devResult
        self.issueAnalyzer.attachmentResult = self.attachmentResult
        self.issueAnalyzer.commentResult = self.commentResult
        self.issueAnalyzer.historyResult = self.historyResult
        self.issueAnalyzer.relationResult = self.relationResult

        self.issueAnalyzer.runMode = utils.RUN_MODE_ANALYSIS
        self.issueAnalyzer.indexType = utils.CACHE_INDEX_TYPE_ANALYSIS

    @classmethod
    def tearDownClass(self):
        '''
        Delete used objects
        '''
        # Delete temporary configuration files
        os.unlink(self.global_conf.name)
        os.unlink(self.project_conf.name)

        # Delete temporary folder
        rmtree(self.tmpDirectory)

        if TEST_RESULTS_ON_FILE:
            stop_logfile("issueAnalyzer_test.log")

    def test_utilsLibrary(self):
        '''
        Tests issue analyzer's utils library
        '''
        # convertToDateTime()
        utilsMsg = "Function codeface.issueanalyzer.common_utils.convertToDateTime() is broken"
        self.assertEqual(utils.convertToDateTime("2018-08-25T15:54:15Z"), datetime.datetime(2018,8,25,15,54,15), utilsMsg)

        # encodeWithUTF8()
        utilsMsg = "Function codeface.issueanalyzer.common_utils.encodeWithUTF8() is broken"
        self.assertEqual(utils.encodeWithUTF8(u"\u1f08\u03b3\u03ba\u03ce\u03bd"), "\xe1\xbc\x88\xce\xb3\xce\xba\xcf\x8e\xce\xbd", utilsMsg)

        # encodeURIWithUTF8()
        utilsMsg = "Function codeface.issueanalyzer.common_utils.encodeURIWithUTF8() is broken"
        self.assertEqual(utils.encodeURIWithUTF8("https://bugzilla.mozilla.org/rest/bug?id=35"), "https%3A//bugzilla.mozilla.org/rest/bug%3Fid%3D35", utilsMsg)

        # getUrlByRunMode()
        utilsMsg = "Function codeface.issueanalyzer.common_utils.getUrlByRunMode() is broken"
        self.assertEqual(utils.getUrlByRunMode("bugzilla.url/bugs", utils.RUN_MODE_ANALYSIS), "bugzilla.url/bugs", utilsMsg)
        self.assertEqual(utils.getUrlByRunMode("bugzilla.url/bugs", utils.RUN_MODE_TEST), "sgub/lru.allizgub", utilsMsg)        

        # safeDiv()
        utilsMsg = "Function codeface.issueanalyzer.common_utils.safeDiv() is broken"
        self.assertEqual(utils.safeDiv(42,0,0), 0, utilsMsg)
        self.assertEqual(utils.safeDiv(42,1,0), 42, utilsMsg)

        # safeGetDeveloper()
        utilsMsg = "Function codeface.issueanalyzer.common_utils.safeGetDeveloper() is broken"

        res = utils.safeGetDeveloper(self.devResult, "mike@joe.url", ["id", "name", "real_name"])
        self.assertEqual(res, [{'real_name': u'Mike Joe', 'id': 1, 'name': u'mike@joe.url'}, 1], utilsMsg)

        res = utils.safeGetDeveloper(self.devResult, "null@test.url", ["id", "name", "real_name"])
        self.assertEqual(res, [{'real_name': 0, 'id': 0, 'name': 0}, 0], utilsMsg)

        # safeSetDeveloper()
        utilsMsg = "Function codeface.issueanalyzer.common_utils.safeSetDeveloper() is broken"

        res = utils.safeSetDeveloper(self.devResult, "mike@joe.url", "id", 2, ["id", "name", "real_name"])
        self.assertEqual(self.devResult["mike@joe.url"], {'real_name': u'Mike Joe', 'id': 2, 'name': u'mike@joe.url'}, utilsMsg)
        self.assertEqual(res, 1, utilsMsg)

        res = utils.safeSetDeveloper(self.devResult, "null@test.url", "id", 1, ["id", "name", "real_name"])
        self.assertEqual(self.devResult["null@test.url"], {'real_name': 0, 'id': 1, 'name': 0}, utilsMsg)
        self.assertEqual(res, 0, utilsMsg)

    def test_cacheLibrary(self):
        '''
        Tests issue analyzer's cache library
        '''
        calculatedIdxBug = os.path.join(self.fakeDir, self.idxBugName)
        calculatedIdxDev = os.path.join(self.fakeDir, self.idxDevName)
        calculatedIdxRel = os.path.join(self.fakeDir, self.idxRelName)
        calculatedIdxAtc = os.path.join(self.fakeDir, self.idxAtcName)
        calculatedIdxCom = os.path.join(self.fakeDir, self.idxComName)
        calculatedIdxHis = os.path.join(self.fakeDir, self.idxHisName)

        # get_path()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.get_path() is broken"
        self.assertEqual(cache.get_path(self.fakeDir, self.urlResult[utils.KEY_ITEMS_BUGS]), calculatedIdxBug, cacheMsg)

        # get_index_path()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.get_index_path() is broken"
        self.assertEqual(cache.get_index_path(self.issueAnalyzer, False), "", cacheMsg)
        self.assertEqual(cache.get_index_path(self.issueAnalyzer, True), os.path.join(self.fakeDir, utils.CACHE_ANALYSIS_INDEX_FILE), cacheMsg)

        self.issueAnalyzer.indexType = utils.CACHE_INDEX_TYPE_TEST
        self.assertEqual(cache.get_index_path(self.issueAnalyzer, False), "", cacheMsg)
        self.assertEqual(cache.get_index_path(self.issueAnalyzer, True), os.path.join(self.fakeDir, utils.CACHE_TEST_INDEX_FILE), cacheMsg)
        self.issueAnalyzer.indexType = utils.CACHE_INDEX_TYPE_ANALYSIS

        # put_data()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.put_data() is broken"
        fakePath = cache.put_data(self.fakeDir, self.urlResult[utils.KEY_ITEMS_BUGS], self.bugResult)
        self.assertEqual(fakePath, calculatedIdxBug, cacheMsg)

        # get_data()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.get_data() is broken"
        self.assertEqual(cache.get_data(fakePath), self.bugResult, cacheMsg)

        # create_index() and parse_index()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.create_index() or parse_index() is broken"
        
        fakePath = cache.create_index(self.issueAnalyzer, calculatedIdxBug, calculatedIdxDev, calculatedIdxAtc, calculatedIdxCom, calculatedIdxHis, calculatedIdxRel)
        [idxBug, idxDev, idxAtc, idxCom, idxHis, idxRel] = cache.parse_index(self.issueAnalyzer)        

        self.assertEqual(calculatedIdxBug, idxBug, cacheMsg)
        self.assertEqual(calculatedIdxDev, idxDev, cacheMsg)
        self.assertEqual(calculatedIdxAtc, idxAtc, cacheMsg)
        self.assertEqual(calculatedIdxCom, idxCom, cacheMsg)
        self.assertEqual(calculatedIdxHis, idxHis, cacheMsg)
        self.assertEqual(calculatedIdxRel, idxRel, cacheMsg)

        # delete_file()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.delete_file() is broken"
        self.assertTrue(os.path.exists(calculatedIdxBug), cacheMsg)
        cache.delete_file(calculatedIdxBug)
        self.assertFalse(os.path.exists(calculatedIdxBug), cacheMsg)

        # indexPathExists()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.indexPathExists() is broken"
        self.assertTrue(cache.indexPathExists(self.issueAnalyzer), cacheMsg)

        # delete_data()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.delete_data() is broken"
        self.assertTrue(os.path.exists(self.fakeDir), cacheMsg)
        cache.delete_data(self.issueAnalyzer)
        self.assertFalse(os.path.exists(self.fakeDir), cacheMsg)

        # indexPathExists()
        cacheMsg = "Function codeface.issueanalyzer.issue_cache.indexPathExists() is broken"
        self.assertFalse(cache.indexPathExists(self.issueAnalyzer), cacheMsg)

    def test_configurationParameters(self):
        '''
        Tests that configuration parameters work properly
        ''' 
        # Check generic parameters
        self.assertEqual(self.conf["dbhost"], "localhost")
        self.assertEqual(self.conf["dbuser"], "codeface")
        self.assertEqual(self.conf["dbpwd"], "codeface")
        self.assertEqual(self.conf["dbname"], "codeface")
        self.assertEqual(self.conf["project"], "theproject")
        self.assertEqual(self.conf["idServicePort"], 8080)
        self.assertEqual(self.conf["idServiceHostname"], "localhost")
        self.assertEqual(self.conf["repo"], "therepo")
        self.assertEqual(self.conf["description"], "the description")
        self.assertEqual(self.conf["ml"], "the mailing list")
        self.assertEqual(self.conf["revisions"], ["v1", "v2"])
        self.assertEqual(self.conf["rcs"],  ["v1rc0", "v2rc0"])
        self.assertEqual(self.conf["tagging"], "tag")

        # Check issue analyzer specific's parameters
        self.assertEqual(self.conf["issueAnalyzerProjectName"], "Bugzilla Core")
        self.assertEqual(self.conf["issueAnalyzerType"], "bugzilla")
        self.assertEqual(self.conf["issueAnalyzerURL"], "bugzilla.url")
        self.assertEqual(self.conf["issueAnalyzerProduct"], "Bugzilla Project")
        self.assertEqual(self.conf["issueAnalyzerTimeIncrement"], 1.1)
        self.assertEqual(self.conf["issueAnalyzerAvailability"], 0.2)
        self.assertEqual(self.conf["issueAnalyzerCollaborativity"], 0.15)
        self.assertEqual(self.conf["issueAnalyzerCompetency"], 0.15)
        self.assertEqual(self.conf["issueAnalyzerProductivity"], 0.3)
        self.assertEqual(self.conf["issueAnalyzerReliability"], 0.2)
        self.assertEqual(self.conf["issueAnalyzerBugOpenedDays"], 60)
        self.assertEqual(self.conf["issueAnalyzerBugFixedDays"], 90)
        self.assertEqual(self.conf["issueAnalyzerPriority1"], "P1")
        self.assertEqual(self.conf["issueAnalyzerPriority2"], "P2")
        self.assertEqual(self.conf["issueAnalyzerSeverity1"], "blocker")
        self.assertEqual(self.conf["issueAnalyzerSeverity2"], "critical")
        self.assertEqual(self.conf["issueAnalyzerSeverity3"], "major")
        self.assertEqual(self.conf["issueAnalyzerSeverity4"], "normal")
        self.assertEqual(self.conf["issueAnalyzerSeverity5"], "minor")
        self.assertEqual(self.conf["issueAnalyzerSeverity6"], "trivial")
        self.assertEqual(self.conf["issueAnalyzerSeverity7"], "enhancement")

    def test_storeAndGetOnCache(self):
        '''
        Tests that store on cache and get from it work properly
        '''        
        # Store on cache
        cache.storeOnCache(self.issueAnalyzer)

        # Get from cache
        cache.getFromCache(self.issueAnalyzer)

        # Compare the results
        bugMsg = "Cache storage of bugs is broken"
        self.assertEqual(self.bugResult, self.issueAnalyzer.bugResult, bugMsg)

        developerMsg = "Cache storage of developers is broken"
        self.assertEqual(self.devResult, self.issueAnalyzer.devResult, developerMsg)

        attachmentMsg = "Cache storage of attachments is broken"
        self.assertEqual(self.attachmentResult, self.issueAnalyzer.attachmentResult, attachmentMsg)

        commentMsg = "Cache storage of comments is broken"
        self.assertEqual(self.commentResult, self.issueAnalyzer.commentResult, commentMsg)

        historyMsg = "Cache storage of history is broken"
        self.assertEqual(self.historyResult, self.issueAnalyzer.historyResult, historyMsg)

        relationMsg = "Cache storage of relations is broken"
        self.assertEqual(self.relationResult, self.issueAnalyzer.relationResult, relationMsg)

    def test_storeAndGetOnDatabase(self):
        '''
        Tests that store on database and get from it work properly
        '''
        self.projectId = bugzilla.analyze(self.issueAnalyzer)
        issue_tables = self.dbm.get_data_stored(self.projectId)

        bugCheck = True
        if len(issue_tables[utils.KEY_ITEMS_BUGS]) > 0:
            result = issue_tables[utils.KEY_ITEMS_BUGS][0]
            
            issueId = result[0]
            projectId = result[1]
            summary = result[2]
            component = result[3]
            creationTime = result[4]
            creator = result[5]
            assignedTo = result[6]
            priority = result[7]
            severity = result[8]
            status = result[9]
            resolution = result[10]
            isOpen = result[11]
            votes = result[12]
            commentCount = result[13]
            keywords = result[14]
            lastResolved = result[15]

            bugInserted = self.bugResult[issueId]

            bugCheck = ((bugInserted["id"] == issueId) and (self.projectId == projectId) and
                        (bugInserted["summary"] == summary) and (bugInserted["component"] == component) and
                        (utils.convertToDateTime(bugInserted["creation_time"]) == creationTime) and (bugInserted["creator"] == creator) and
                        (bugInserted["assigned_to"] == assignedTo) and (bugInserted["priority"] == priority) and
                        (bugInserted["severity"] == severity) and (bugInserted["status"] == status) and
                        (bugInserted["resolution"] == resolution) and (bugInserted["is_open"] == isOpen) and
                        (bugInserted["votes"] == votes) and (bugInserted["comment_count"] == commentCount) and
                        (",".join(x for x in bugInserted["keywords"]) == keywords) and (bugInserted["cf_last_resolved"] == lastResolved))

        bugMsg = "Database storage of bugs is broken"
        self.assertTrue(bugCheck, bugMsg)

        developerCheck = True
        if len(issue_tables[utils.KEY_ITEMS_DEVELOPERS]) > 0:
            result = issue_tables[utils.KEY_ITEMS_DEVELOPERS][0]
            
            developerName = result[0]
            developerRealName = result[1]
            projectId = result[2]
            developerId = result[3]

            developerInserted = self.devResult[developerName]

            developerCheck = ((developerInserted["name"] == developerName) and (developerInserted["real_name"] == developerRealName) and
                              (self.projectId == projectId) and (developerInserted["id"] == developerId))

        developerMsg = "Database storage of developers is broken"
        self.assertTrue(developerCheck, developerMsg)

        attachmentCheck = True
        if len(issue_tables[utils.KEY_ITEMS_ATTACHMENTS]) > 0:
            result = issue_tables[utils.KEY_ITEMS_ATTACHMENTS][0]
            
            attachmentId = result[0]
            projectId = result[1]
            issueId = result[2]
            creator = result[3]
            creationTime = result[4]
            isObsolete = result[5]
            isPatch = result[6]
            isPrivate = result[7]
            size = result[8]
            positiveReviews = result[9]

            attachmentsInserted = self.attachmentResult[issueId]
            for att in attachmentsInserted:
                if att["id"] == attachmentId:
                    attachmentInserted = att
                    break

            attachmentCheck = ((attachmentInserted["id"] == attachmentId) and (self.projectId == projectId) and
                               (attachmentInserted["bug_id"] == issueId) and (attachmentInserted["creator"] == creator) and
                               (utils.convertToDateTime(attachmentInserted["creation_time"]) == creationTime) and (attachmentInserted["is_obsolete"] == isObsolete) and
                               (attachmentInserted["is_patch"] == isPatch) and (attachmentInserted["is_private"] == isPrivate) and
                               (attachmentInserted["size"] == size) and (attachmentInserted["positive_reviews"] == positiveReviews))

        attachmentMsg = "Database storage of attachments is broken"
        self.assertTrue(attachmentCheck, attachmentMsg)      

        commentCheck = True
        if len(issue_tables[utils.KEY_ITEMS_COMMENTS]) > 0:
            result = issue_tables[utils.KEY_ITEMS_COMMENTS][0]
            
            commentId = result[0]
            projectId = result[1]
            issueId = result[2]
            author = result[3]
            time = result[4]
            rawText = result[5]

            commentsInserted = self.commentResult[issueId]
            for com in commentsInserted:
                if com["id"] == commentId:
                    commentInserted = com
                    break

            commentCheck = ((commentInserted["id"] == commentId) and (self.projectId == projectId) and
                            (commentInserted["bug_id"] == issueId) and (commentInserted["author"] == author) and
                            (utils.convertToDateTime(commentInserted["creation_time"]) == time) and (commentInserted["raw_text"] == rawText))

        commentMsg = "Database storage of comments is broken"
        self.assertTrue(commentCheck, commentMsg)

        historyCheck = True
        if len(issue_tables[utils.KEY_ITEMS_HISTORY]) > 0:
            result = issue_tables[utils.KEY_ITEMS_HISTORY][0]
            
            issueId = result[0]
            projectId = result[1]
            who = result[2]
            time = result[3]
            added = result[4]
            removed = result[5]
            #attachmentId = result[6]
            fieldName = result[7]            

            historyInserted = self.historyResult[issueId]
            changesInserted = historyInserted["history"][0]["changes"]
            for chg in changesInserted:
                if chg["removed"] == removed and chg["field_name"] == fieldName and chg["added"] == added:
                    changeInserted = chg
                    break

            historyCheck = ((historyInserted["id"] == issueId) and (self.projectId == projectId) and
                            (historyInserted["history"][0]["who"] == who) and (utils.convertToDateTime(historyInserted["history"][0]["when"]) == time) and
                            (changeInserted["added"] == added) and (changeInserted["removed"] == removed) and
                            (changeInserted["field_name"] == fieldName))

        historyMsg = "Database storage of history is broken"
        self.assertTrue(historyCheck, historyMsg)
        
        relationCheck = True
        if len(issue_tables[utils.KEY_ITEMS_RELATIONS]) > 0:
            resultBlocks = issue_tables[utils.KEY_ITEMS_RELATIONS][0]
            resultDependsOn = issue_tables[utils.KEY_ITEMS_RELATIONS][1]
            
            issueIdBlocks = resultBlocks[0]
            projectIdBlocks = resultBlocks[1]
            relatedIssueIdBlocks = resultBlocks[2]
            relationTypeBlocks = resultBlocks[3]

            issueIdDependsOn = resultDependsOn[0]
            projectIdDependsOn = resultDependsOn[1]
            relatedIssueIdDependsOn = resultDependsOn[2]
            relationTypeDependsOn = resultDependsOn[3]

            relationInserted = self.relationResult[issueId]

            relationCheck = ((self.projectId == projectIdBlocks) and (self.projectId == projectIdDependsOn) and
                                   (relationInserted["blocks"][0] == relatedIssueIdBlocks) and (relationInserted["depends_on"][0] == relatedIssueIdDependsOn) and
                                   (relationTypeBlocks == "blocks") and (relationTypeDependsOn == "depends on"))

        relationMsg = "Database storage of relations is broken"
        self.assertTrue(relationCheck, relationMsg)

        # Remove test data from database
        self.dbm.reset_issue_database(self.projectId)

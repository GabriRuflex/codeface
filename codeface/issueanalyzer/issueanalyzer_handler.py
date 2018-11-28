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
Handler module to manage issue analyzer worker
"""
from logging import getLogger; log = getLogger(__name__)

import codeface.issueanalyzer.bugzilla_analyzer as bugzilla
import codeface.issueanalyzer.common_utils as utils
import codeface.issueanalyzer.issue_cache as cache

from codeface.cluster.idManager import idManager
from codeface.configuration import Configuration
from codeface.dbmanager import DBManager
from codeface.logger import (set_log_level, start_logfile, stop_logfile)
from codeface.util import BatchJobPool

class IssueAnalyzer(object):
    def __init__(self, runMode, codefaceConfig, iaProject, cacheDirectory, flags, qParams, logPath = None, nJobs = 0):
        """Create a new instance of IssueAnalyzer

        Get the configuration files and then creates
        the istances and handle the user's commands.

        Args:
            runMode(str): Run mode of analyzer
            codefaceConfig(str): Path of the Codeface configuration file
            iaProject(str): Path of the project configuration file
                issueAnalyzerProjectName: Name of project
                issueAnalyzerType: Type of project
                issueAnalyzerURL: URL of bugtracker
                issueAnalyzerProduct: Name of project's product
                issueAnalyzerTimeIncrement: Coefficient of time increment quality parameter
                issueAnalyzerAvailability: Coefficient of availability quality parameter
                issueAnalyzerCollaborativity: Coefficient of collaborativity quality parameter
                issueAnalyzerCompetency: Coefficient of competency quality parameter
                issueAnalyzerProductivity: Coefficient of productivity quality parameter
                issueAnalyzerReliability: Coefficient of reliability quality parameter                
                issueAnalyzerBugOpenedDays: Max days for open bugs
                issueAnalyzerBugFixedDays: Max days for fixed bugs
                issueAnalyzerPriority1-2: Name of priority fields to analyze
                issueAnalyzerSeverity1-7: Name of severity fields to analyze
            cacheDirectory(str): Path of the cache directory
            flags(tuple):
                dropDatabase(bool): If true, database is resetted
                scratchOnly(bool): If true, only scratching is done
                analyzeOnly(bool): If true, only analyzing is done
                deleteCacheOnly(bool): If true, only cache deleting is done
            qParams(tuple):
                issueAnalyzerTimeIncrement(float): Coefficient of time increment quality parameter
                issueAnalyzerAvailability(float): Coefficient of availability quality parameter
                issueAnalyzerCollaborativity(float): Coefficient of collaborativity quality parameter
                issueAnalyzerCompetency(float): Coefficient of competency quality parameter
                issueAnalyzerProductivity(float): Coefficient of productivity quality parameter
                issueAnalyzerReliability(float): Coefficient of reliability quality parameter  
            logPath(str): Path of log file

        Returns None

        Notes:
            Currently only Bugzilla is supported

        """
        # Parse the runMode argument
        self.__runModes = [utils.RUN_MODE_ANALYSIS, utils.RUN_MODE_TEST]
        self.__indexTypes = [utils.CACHE_INDEX_TYPE_ANALYSIS, utils.CACHE_INDEX_TYPE_TEST]
        if runMode == "analysisOnly":
            self.__runModes = [utils.RUN_MODE_ANALYSIS]
            self.__indexTypes = [utils.CACHE_INDEX_TYPE_ANALYSIS]
        elif runMode == "testOnly":
            self.__runModes = [utils.RUN_MODE_TEST]
            self.__indexTypes = [utils.CACHE_INDEX_TYPE_TEST]

        # Start logging on file if needed
        self.logPath = logPath
        if self.logPath is not None:
            start_logfile(self.logPath, "info")

        # Initialize Issue Analyzer's instance
        self.__conf = Configuration.load(codefaceConfig, iaProject)
        self.__cacheDirectory = cacheDirectory
        self.dbm = DBManager(self.__conf)
        self.flags = flags
        self.nJobs = int(nJobs)
        """
        self.pool = BatchJobPool(int(nJobs))
        idm = idManager(dbm, conf)
        """

        if self.__cacheDirectory is None:
            self.__cacheDirectory = utils.CACHE_DEFAULT_DIRECTORY

        # Parse quality parameters:
        # Overwrite the existing parameter if it's re-defined via CLI
        # If it isn't defined, use the default one
        if qParams[0] is not None:
            self.__conf["issueAnalyzerTimeIncrement"] = qParams[0]
        elif "issueAnalyzerTimeIncrement" not in self.__conf.keys():
            self.__conf["issueAnalyzerTimeIncrement"] = utils.DEFAULT_TIME_INCREMENT
        
        if qParams[1] is not None:
            self.__conf["issueAnalyzerAvailability"] = qParams[1]
        elif "issueAnalyzerAvailability" not in self.__conf.keys():
            self.__conf["issueAnalyzerAvailability"] = utils.DEFAULT_COEFF_AVAILABILITY

        if qParams[2] is not None:
            self.__conf["issueAnalyzerCollaborativity"] = qParams[2]
        elif "issueAnalyzerCollaborativity" not in self.__conf.keys():
            self.__conf["issueAnalyzerCollaborativity"] = utils.DEFAULT_COEFF_COLLABORATIVITY

        if qParams[3] is not None:
            self.__conf["issueAnalyzerCompetency"] = qParams[3]
        elif "issueAnalyzerCompetency" not in self.__conf.keys():
            self.__conf["issueAnalyzerCompetency"] = utils.DEFAULT_COEFF_COMPETENCY

        if qParams[4] is not None:
            self.__conf["issueAnalyzerProductivity"] = qParams[4]
        elif "issueAnalyzerProductivity" not in self.__conf.keys():
            self.__conf["issueAnalyzerProductivity"] = utils.DEFAULT_COEFF_PRODUCTIVITY

        if qParams[5] is not None:
            self.__conf["issueAnalyzerReliability"] = qParams[5]
        elif "issueAnalyzerReliability" not in self.__conf.keys():
            self.__conf["issueAnalyzerReliability"] = utils.DEFAULT_COEFF_RELIABILITY

        self.__urlResult = dict()
        self.__bugResult = dict()
        self.__devResult = dict()
        self.__attachmentResult = dict()
        self.__commentResult = dict()
        self.__historyResult = dict()
        self.__relationResult = dict()

        log.info(str("config: {}, project: {}, directory: {} (DEFAULT: {}), index types: {}, flags: {}, qParams: {}, log: {}, jobs: {}").format(
            codefaceConfig, iaProject, self.__cacheDirectory, utils.CACHE_DEFAULT_DIRECTORY, self.__indexTypes, self.flags, qParams, self.logPath, self.nJobs))

    def __del__(self):
        """
        Destroy Issue Analyzer's instance
        """
        # Stop logging on file if needed
        if self.logPath is not None:
            stop_logfile(self.logPath)

    def handle(self):
        """
        Handler of Issue Analyzer
        """
        log.info("Issue analyzer's handler started.")

        if self.flags[0]:
            # Remove data from database if flag "--dropDatabase" is set
            log.info("Deleting entries on database...")
            self.dbm.reset_issue_database()

            return

        # Run routines for each mode
        for runMode, indexType in zip(self.__runModes, self.__indexTypes):
            self.__runMode = runMode
            self.__indexType = indexType

            indexExists = cache.indexPathExists(self)

            if self.flags[3]:
                # Delete cache if flag "--deleteCacheOnly" is set
                if indexType == utils.CACHE_INDEX_TYPE_ANALYSIS:
                    log.info("Deleting files of analysis on cache...")
                else:
                    log.info("Deleting files of test on cache...")

                cache.delete_data(self)
            elif self.flags[2] and not cache.indexPathExists(self):
                # Exit if run mode flag is set but directory isn't set or doesn't exist
                if indexType == utils.CACHE_INDEX_TYPE_ANALYSIS:
                    log.info("Flag of run mode is set but issue directory for analysis isn't set or it doesn't exist.")
                else:
                    log.info("Flag of run mode is set but issue directory for test isn't set or it doesn't exist.")
            else:
                if not self.flags[2]:
                    # Scratch issues from bugzilla if "--analyzeOnly" flag is not set
                    self.scratch()
             
                if not self.flags[1] and cache.indexPathExists(self):
                    # Analyze issues already stored if "--scratchOnly" flag is not set
                    self.analyze()

            log.info("Completed!")

    def scratch(self):
        # Start scratching
        bugzilla.scratch(self)
        
        # Store results on cache
        cache.storeOnCache(self)
        
        """
        jPool = BatchJobPool(jobs)

        for i in range(0, jobs):
            jPool.add(bugzilla.scratch, [conf, buglist])
        jPool.join()
        """

    def analyze(self):
        # Get results from cache
        cache.getFromCache(self) 

        # Start analyzing
        projectId = bugzilla.analyze(self)

        # Get the results
        bugzilla.getResult(self, projectId)

    # self.__conf
    @property
    def conf(self):
        return self.__conf

    # self.__cacheDirectory
    @property
    def cacheDirectory(self):
        return self.__cacheDirectory

    # self.__runMode
    @property
    def runMode(self):
        return self.__runMode

    @runMode.setter
    def runMode(self, runMode):
        self.__runMode = runMode

    # self.__indexType
    @property
    def indexType(self):
        return self.__indexType

    @indexType.setter
    def indexType(self, indexType):
        self.__indexType = indexType

    # self.__urlResult
    @property
    def urlResult(self):
        return self.__urlResult

    @urlResult.setter
    def urlResult(self, urlResult):
        self.__urlResult = urlResult

    # self.__bugResult
    @property
    def bugResult(self):
        return self.__bugResult

    @bugResult.setter
    def bugResult(self, bugResult):
        self.__bugResult = bugResult

    # self.__devResult
    @property
    def devResult(self):
        return self.__devResult

    @devResult.setter
    def devResult(self, devResult):
        self.__devResult = devResult

    # self.__attachmentResult
    @property
    def attachmentResult(self):
        return self.__attachmentResult

    @attachmentResult.setter
    def attachmentResult(self, attachmentResult):
        self.__attachmentResult = attachmentResult

    # self.__commentResult
    @property
    def commentResult(self):
        return self.__commentResult

    @commentResult.setter
    def commentResult(self, commentResult):
        self.__commentResult = commentResult

    # self.__historyResult
    @property
    def historyResult(self):
        return self.__historyResult

    @historyResult.setter
    def historyResult(self, historyResult):
        self.__historyResult = historyResult

    # self.__relationResult
    @property
    def relationResult(self):
        return self.__relationResult

    @relationResult.setter
    def relationResult(self, relationResult):
        self.__relationResult = relationResult

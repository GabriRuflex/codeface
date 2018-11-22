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
Issue analyzer's utils module
"""

import urllib
import datetime as dt

import os
from os.path import expanduser

# Analyzer's run modes
RUN_MODE_ANALYSIS = 0
RUN_MODE_TEST = 1

# Definitions for analysis
DEFAULT_TIME_INCREMENT = 1.1

DEFAULT_COEFF_AVAILABILITY = 0.2
DEFAULT_COEFF_COLLABORATIVITY = 0.15
DEFAULT_COEFF_COMPETENCY = 0.15
DEFAULT_COEFF_PRODUCTIVITY = 0.3
DEFAULT_COEFF_RELIABILITY = 0.2

# Dict keys to handle scratching's results
KEY_ITEMS_BUGS = "bugs"
KEY_ITEMS_DEVELOPERS = "developers"
KEY_ITEMS_ATTACHMENTS = "attachments"
KEY_ITEMS_COMMENTS = "comments"
KEY_ITEMS_HISTORY = "history"
KEY_ITEMS_RELATIONS = "relations"

QUERY_TYPE_ALL_ASSIGNMENTS = 0
QUERY_TYPE_ASSIGNMENTS_STATS = 1

# Cache parameters to store scratching's results
CACHE_INDEX_TYPE_ANALYSIS = 0
CACHE_INDEX_TYPE_TEST = 1

CACHE_DEFAULT_DIRECTORY = os.path.join(expanduser("~"), "Issue Analyzer Cache")
CACHE_ANALYSIS_INDEX_FILE = "issueAnalyzerAnalysisIndex"
CACHE_TEST_INDEX_FILE = "issueAnalyzerTestIndex"

def convertToDateTime(oldDate):
    """Convert a Bugzilla timestamp into a SQL compatible DateTime object

    Args:
        oldDate (string): The date string given by the bugtracker

    Returns (datetime.datetime): A datetime.datetime object

    """ 
    result = None
    if oldDate is not None:
        result = dt.datetime.strptime(oldDate, "%Y-%m-%dT%H:%M:%SZ")

    return result

def encodeWithUTF8(string):
    """Encode a string with UTF-8

    Args:
        string (string): A string not encoded

    Returns (string): A string object

    """
    return string.encode('utf-8')

def encodeURIWithUTF8(uri):
    """Encode a URI with UTF-8

    Args:
        string (string): An URI string not encoded

    Returns (string): An URI string object

    """
    return urllib.quote(encodeWithUTF8(uri))

def getUrlByRunMode(url, runMode):
    """Get correct URL

    Args:
        url (string): The URL to use
        runMode (numeric): Run mode currently in use

    Returns (string): The numeric operation's result

    """
    result = url
    # If runMode is TEST, just flip the URL
    if runMode == RUN_MODE_TEST:
        result = result[::-1]

    return result

def safeDiv(op1, op2, defaultResult):
    """Safetly divide

    Args:
        op1 (numeric): The first numeric operator
        op2 (numeric): The second numeric operator
        defaultResult (numeric): The default result if op1/op2 is invalid

    Returns (numeric): The numeric operation's result

    """
    result = defaultResult
    try:
        result = op1/op2
    except:
        pass
    return result

def safeGetDeveloper(devs, dev, keys):
    """Safetly get developers data

    Args:
        devs (dict): The developers' dict
        dev (object): The developer key to find
        keys (tuple): A dict's tuple of developer's keys to return

    Returns (tuple): A tuple object

    """
    if dev in devs.keys():
        devDetails = devs[dev]
        d = [devDetails[x] for x in keys]
        d.append(1)
    else:
        d = [0 for x in keys]
        d.append(0)

    # Populate the dict
    i = 0
    r = dict()
    for key in keys:
        r[key] = d[i]
        i = i+1

    # Create the result
    result = [r, d[-1]]
    return result

def safeSetDeveloper(devs, dev, key, value, keys):
    """Safetly set developers data

    Args:
        devs (dict): The developers' dict
        dev (object): The developer key to find
        key (object): The developer's sub-key to find
        value (object): The developer's sub-value to set        
        keys (tuple): A dict's tuple of developer's keys to return

    Returns (dict): A dict object

    """
    result = safeGetDeveloper(devs, dev, keys)
    result[0][key] = value

    # Update the developer data
    devs[dev] = result[0]

    # Result only if it's the first assignment for the developer
    return result[1]

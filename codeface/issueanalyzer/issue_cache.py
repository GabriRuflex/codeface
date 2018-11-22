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
Issue analyzer's cache module to store scratching's results
"""

import os
import hashlib
import pickle
from shutil import rmtree

import codeface.issueanalyzer.common_utils as utils

from logging import getLogger; log = getLogger(__name__)

def get_path(directory, url):
    """Calculate the path for cache file

    Args:
        directory (str): Main directory path
        url (str): URL used to create the file path by an unique hash

    Returns (string): Absolute path

    """
    # Create a teorically unique hash from url
    h = str(hashlib.sha256(url).hexdigest())
    
    return os.path.join(os.path.abspath(directory), h[:4], h[4:8], h[8:])

def get_index_path(issueAnalyzer, createDirectory):
    """Get the index file's path

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle
        createDirectory (bool): If true and directory doesn't exist, create it

    Returns (string): Absolute index file path

    """
    # Get the index path
    indexFile = utils.CACHE_ANALYSIS_INDEX_FILE if issueAnalyzer.indexType == utils.CACHE_INDEX_TYPE_ANALYSIS else utils.CACHE_TEST_INDEX_FILE
    path = os.path.join(issueAnalyzer.cacheDirectory, indexFile)

    # If index file doesn't exist, return empty path
    if not os.path.isfile(path):
        if createDirectory:
            # Check if directory exists
            if not os.path.exists(os.path.dirname(path)):
                try:
                    os.makedirs(os.path.dirname(path))
                except:
                    pass
        else:
            path = ""

    return path

def get_data(path):
    """Read data from file

    Args:
        path (str): File path

    Returns (object): File content

    """
    with open(path, 'r') as file:
        data = pickle.load(file)

    return data

def put_data(directory, url, data):
    """Put data on file

    Args:
        directory (str): Directory path        
        url (str): URL used to create unique filename
        data (str): Data to put on file

    Returns (object): File path

    """
    # Get data path
    path = get_path(directory, url)

    # Check if directory exists
    if not os.path.exists(os.path.dirname(path)):
        try:
            os.makedirs(os.path.dirname(path))
        except:
            pass

    # Write data on file
    with open(path,'w+') as file:
        pickle.dump(data, file)

    return path

def create_index(issueAnalyzer, idxBug, idxDev, idxAtc, idxCom, idxHis, idxRel):
    """Create main index file

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle
        idxBug (dict): Bug dict index path
        idxDev (dict): Developer dict index path
        idxAtc (dict): Attachment dict index path
        idxCom (dict): Comment dict index path
        idxHis (dict): History dict index path
        idxRel (dict): Relation dict index path

    Returns (string): Index file path

    """
    # Get data path
    path = get_index_path(issueAnalyzer, True)

    # Write data on file
    with open(path,'w+') as file:
        file.write(idxBug + "\n")
        file.write(idxDev + "\n")
        file.write(idxAtc + "\n")
        file.write(idxCom + "\n")
        file.write(idxHis + "\n")
        file.write(idxRel + "\n")

    return path

def parse_index(issueAnalyzer):
    """Get single indexes from main index file
    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle

    Returns (tuple): Index files' path

    """
    # Get data path
    path = get_index_path(issueAnalyzer, False)

    # Check if index exists
    if path == "":
        return []

    # Read data on file
    lines = []
    with open(path,'r') as file:
        lines = [line.rstrip('\n') for line in file]

    return lines

def delete_data(issueAnalyzer):
    """Delete all data on a directory

    Args:
       issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle

    Returns None

    """
    directory = issueAnalyzer.cacheDirectory
    
    # Get files' path on cache
    paths = parse_index(issueAnalyzer)

    # Check if index exists
    index = get_index_path(issueAnalyzer, False)
    if index == "":
        return
    else:
        # Delete cache index
        delete_file(index)

    # Delete cache files
    if not paths == []:
        for path in paths:
            # Remove file
            delete_file(path)
            
            # Remove each empty directory
            c = 0
            folder = os.path.join(directory, path[len(directory):].split("/")[1])
            for root, dirs, files in os.walk(folder):
                c = c + len(files)
            if (c == 0) and os.path.exists(folder):
                rmtree(folder)

    # Delete cache folder if empty
    if os.listdir(directory) == []:
        os.rmdir(directory)

def delete_file(path):
    """Safetly delete a single file

    Args:
        path (str): File path

    Returns None

    """
    # Delete a file given its path
    try:
        os.remove(path)
    except:
        pass

def indexPathExists(issueAnalyzer):
    """Check if index path exists

    Args:
       issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle

    Returns bool: If true, it exists

    """    
    return get_index_path(issueAnalyzer, False) != ""

def storeOnCache(issueAnalyzer):
    """Store data on cache

    Args:
       issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to handle

    Returns None

    """
    urlResult = issueAnalyzer.urlResult
    bugResult = issueAnalyzer.bugResult
    devResult = issueAnalyzer.devResult
    attachmentResult = issueAnalyzer.attachmentResult
    commentResult = issueAnalyzer.commentResult
    historyResult = issueAnalyzer.historyResult
    relationResult = issueAnalyzer.relationResult

    cacheDirectory = issueAnalyzer.cacheDirectory
    
    # Delete cache
    delete_data(issueAnalyzer)

    # Store the result on the cache directory
    idxBug = put_data(cacheDirectory, urlResult[utils.KEY_ITEMS_BUGS], bugResult)
    idxDev = put_data(cacheDirectory, urlResult[utils.KEY_ITEMS_DEVELOPERS], devResult)
    idxAtc = put_data(cacheDirectory, urlResult[utils.KEY_ITEMS_ATTACHMENTS], attachmentResult)
    idxCom = put_data(cacheDirectory, urlResult[utils.KEY_ITEMS_COMMENTS], commentResult)
    idxHis = put_data(cacheDirectory, urlResult[utils.KEY_ITEMS_HISTORY], historyResult)
    idxRel = put_data(cacheDirectory, urlResult[utils.KEY_ITEMS_RELATIONS], relationResult)

    # Create the index file
    create_index(issueAnalyzer, idxBug, idxDev, idxAtc, idxCom, idxHis, idxRel)

def getFromCache(issueAnalyzer):
    """Get data from cache

    Args:
        issueAnalyzer (codeface.issueanalyzer.issueanalyzer_handler.IssueAnalyzer): Issue Analyzer instance to update

    Returns None

    """    
    # Read issues index from the given directory
    [idxBug, idxDev, idxAtc, idxCom, idxHis, idxRel] = parse_index(issueAnalyzer)

    # Read issues from the given directory
    bugResult = get_data(idxBug)
    devResult = get_data(idxDev)
    attachmentResult = get_data(idxAtc)
    commentResult = get_data(idxCom)
    historyResult = get_data(idxHis)
    relationResult = get_data(idxRel)

    issueAnalyzer.bugResult = bugResult
    issueAnalyzer.devResult = devResult
    issueAnalyzer.attachmentResult = attachmentResult
    issueAnalyzer.commentResult = commentResult
    issueAnalyzer.historyResult = historyResult
    issueAnalyzer.relationResult = relationResult

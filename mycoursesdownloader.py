#!/usr/bin/env python3

"""
The MIT License (MIT)

Copyright (c) 2015 Colum McGaley <cxm7688@rit.edu>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import requests
from bs4 import BeautifulSoup
import re
import os
from urllib.parse import unquote
import argparse
import sys
import getpass
import json
import datetime

# Constants
D2L_BASEURL = "https://mycourses.rit.edu"


def output(level="Info", message=""):
    print("[{0}][{1:>8}] {2}".format(str(datetime.datetime.now()), level, message))


# basically, mkdir -p /blah/blah/blah
def mkdir_recursive(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        output(level="Error", message="Exception: {}".format(e))
        exit(1)


def safeFilePath(path):
    ## Fucking unicode
    path = ''.join([i if ord(i) < 128 else ' ' for i in path])

    bad = ["<", ">", ":", "|", "?", "*", " / ", " \ "]
    for char in bad:
        path = path.replace(char, " ")
    return path

def download(url, path):
    SIZE = 0
    file = session.get(url, stream=True)

    if file.status_code == 302:  # D2L, you don't fucking redirect a 404/403 error.
        output(level="Error", message="Requested file is Not Found or Forbidden")

    if not os.path.isdir(safeFilePath(path)):
        output(level="Info", message="Directory does not exist.")
        output(level="Debug", message=safeFilePath(path))
        mkdir_recursive(safeFilePath(path))
    try:
        name = unquote(file.headers['content-disposition'].split(' ')[2].split("\"")[1])
        path += name

        output(level="Progress", message="Downloading " + safeFilePath(name))

        with open(safeFilePath(path), 'wb') as f:
            for chunk in file.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()
                    SIZE += 1024

    except Exception as e:
        output(level="Error", message="Error: {}. File ID: {}".format(e, file_id))
        output(level="Debug", message="Path " + url)

    return SIZE


# Start main program
if __name__ == "__main__":

    #
    # Set up Required Variables to Auth to MyCourses
    #

    if sys.version_info[0] < 3:
        print("I need python 3+")
        exit()

    parser = argparse.ArgumentParser(description='Downloads all course contents from MyCourses')
    parser.add_argument('-u', help='Your RIT Username that you use for MyCourses')
    parser.add_argument('-d', help='The directory where the files will be downloaded')
    parser.add_argument('--force-review', help="Force review of each class", action='store_true')
    parser.add_argument('--skip-review', help="Don't prompt for class review", action='store_true')
    parser.add_argument('--skip-classes', help="List of Classes to skip. Enter a class followed by a space. Entered "
                                               "text will be matched to the start of  the string. So, `NSSA.24` will be"
                                               " matched to /NSSA\.24(.*)/g", nargs='+')
    parser.add_argument('--download-classes', nargs='+', help='List of classes to download. Enter a class followed by'
                                                              ' a space. Text will be matched to the start of the '
                                                              'string.')

    args = parser.parse_args()

    if args.u is None:
        args.u = input("RIT Username: ")

    password = getpass.getpass("RIT Password: ")

    if args.d is None:
        args.d = input("Enter download directory: ")
        if not args.d:
            args.d = os.path.join(os.getcwd(),"MyCoursesDownloaderOutput")

    workingDirectory = os.path.join(os.getcwd(),args.d)

    if not os.path.exists(workingDirectory):
        output(level="Warning", message="Directory does not exist. Creating")
        mkdir_recursive(workingDirectory)

    URLS = []   # [("22222", "PLOS.140"), ("11111", "NSSA.220")]

    #
    # Start the Session
    #
    session = requests.Session()
    # Log in. Now with Shibboleth support!
    import pprint
    r = session.get(D2L_BASEURL + '/Shibboleth.sso/Login?entityID=https://shibboleth.main.ad.rit.edu/idp/shibboleth&target=https%3A%2F%2Fmycourses.rit.edu%2Fd2l%2FshibbolethSSO%2Flogin.d2l', allow_redirects=True)

    rs = session.post(r.url, data={
        'j_username': args.u,
        'j_password': password,
        '_eventId_proceed': ''
    })
    if rs.status_code == 401:
        output(level="Error", message="Shibboleth rejected your username and/or password.")
        exit()


    # 06/11/16 - Fuck. D2l is much more secure that RIT's Shibboleth implementations
    # Ok. So. I hit Shibboleth.sso/SAML2/POST, and in my browser I get two 302 redirects and end up at lelogin.d2.
    # Here, I'm getting bumped to a 500 error page (Which is fucking stupid D2l. Dont 302 error pages)
    # after the initial hit.

    # 06/12/16 - Ok, so it wasn't a cookie issue. The issue here is that Shibboleth was returning an unicode encoded
    # RelayState, which FireFox and Chrome handle correctly. The problem was that Requests/urllib3 does not decode it,
    # and was passing the raw unicoded string onto D2l which was causing it to choke. U
    dta = {
        # TODO Make this dynamic and read the data from the response one I figure out how to decode the stuff. .decode() does not work
        "RelayState": "https://mycourses.rit.edu/d2l/shibbolethSSO/login.d2l",
        "SAMLResponse": re.search('(<input type="hidden" name="SAMLResponse" value=").*("/>)', rs.text).group(0).replace('<input type="hidden" name="SAMLResponse" value="', '').replace('"/>', '')
    }

    rq = session.post(D2L_BASEURL + "/Shibboleth.sso/SAML2/POST", data=dta, allow_redirects=True)
    session.get(D2L_BASEURL + "/d2l/lp/auth/login/ProcessLoginActions.d2l")

    output(level="Info", message="Good Login")

    r = session.get(D2L_BASEURL + "/d2l/home")
    soup = BeautifulSoup(r.text, "html.parser")

    # Get the session token required for ajax queries
    xsrf = str(soup.findAll("script")[-1]).splitlines()
    for line in xsrf:
        if "D2L.LP.Web.Authentication.Xsrf.Init" in line:
            xsrf = line.split("\"")[16][:-1]
            output(level="Debug", message="Xsrf is " + xsrf)

    # Switch to the current courses.
    data = {
        'widgetId': "11",
        "_d2l_prc$childScopeCounters": "filtersData:0",
        "_d2l_prc$headingLevel": "3",
        "_d2l_prc$scope": "",
        "_d2l_prc$hasActiveForm": "false",
        'isXhr': 'true',
        'requestId': '3',
        "d2l_referrer": xsrf,
    }
    r = session.post(D2L_BASEURL + "/d2l/le/manageCourses/widget/myCourses/6605/ContentPartial?defaultLeftRightPixelLength=10&defaultTopBottomPixelLength=7", data=data)
    # d2l changed to ajax. woo!
    soup = BeautifulSoup(json.loads(r.text.replace("while(1);", ""))['Payload']['Html'], "html.parser")
    resp = soup.findAll(attrs={'class': 'd2l-collapsepane-content'})
    uvA = resp[0].findAll('a', attrs={'class':'d2l-left'})
    for url in uvA:
        url_code = url['href'].replace('/d2l/lp/ouHome/home.d2l?ou=', '')
        title = url['title'].split(' ')[1]
        URLS.append((url_code, title))

    # Now, switch to the other section that lists all the old courses.
    data = {
        'widgetId': "11",
        "placeholderId$Value": "d2l_1_12_592",
        'selectedRoleId': "618",    # This will proably change in the future
        "_d2l_prc$headingLevel": "3",
        "_d2l_prc$scope": "",
        "_d2l_prc$hasActiveForm": "false",
        'isXhr': 'true',
        'requestId': '3',
        "d2l_referrer": xsrf,
    }
    r = session.post(D2L_BASEURL + "/d2l/le/manageCourses/widget/myCourses/6605/ContentPartial?defaultLeftRightPixelLength=10&defaultTopBottomPixelLength=7", data=data)
    r = session.get(D2L_BASEURL + "/d2l/home")
    soup = BeautifulSoup(r.text, "html.parser")
    resp = soup.findAll(attrs={'class': 'd2l-collapsepane-content'})
    for tresp in resp:
        uvA = tresp.findAll('a', attrs={'class':'d2l-left'})
        for url in uvA:
            url_code = url['href'].replace('/d2l/lp/ouHome/home.d2l?ou=', '')
            title = url['title'].split(' ')[1].replace("/","_")
            URLS.append((url_code, title))

    # Check for duplicate entries.
    URLS = set(tuple(element) for element in URLS)

    output(level="Info", message="Found {} classes.".format(str(len(URLS))))

    if args.download_classes is not None:
        output(level="Info", message="Only downloading selected classes")
        # Assume skipping review
        args.skip_review = True
        # We need to loop through each course and each allow_class
        TURLS = []
        pattern = "|".join(map(str, args.download_classes))
        for rit_class in URLS:
            if re.match(pattern, rit_class[1]) is not None:    # We found a match
                TURLS.append(rit_class)

        output(level="Info", message=("Deleted " + str(len(URLS) - len(TURLS))))
        URLS = []
        URLS = TURLS

    if args.skip_classes is not None:
        args.skip_review = True
        # We need to loop through each course and each skip_classes
        output(level="Info", message="Removing classes")
        TURLS = []
        pattern = "|".join(map(str, args.skip_classes))
        for rit_class in URLS:
            if re.match(pattern, rit_class[1]) is None:    # We didn't found a match
                TURLS.append(rit_class)

        output(level="Info", message=("Deleted " + str(len(URLS) - len(TURLS))))
        URLS = []
        URLS = TURLS

    if args.force_review:
        output(level="Debug", message="Reviewing Courses")
        user_response = "r"
    elif args.skip_review:
        output(level="Debug", message="Skipping review")
        user_response = "s"
    else:
        print("\nI found {} classes.".format(str(len(URLS))))
        print("Would you like to review them?")
        print("Press r followed by enter to review or just press enter...")

        user_response = input("? ")

    # copy URLS
    TURLS = []

    if user_response == "r":
        print("\nPress d followed by enter to skip class. Press enter to accept.\n")
        for rit_class in URLS:
            resp = input(rit_class[1] + " ? ")
            if resp != "d":
                TURLS.append(rit_class)
        output(level="Info", message=("Deleted " + str(len(URLS) - len(TURLS))))
        URLS = []
        URLS = TURLS
    else:
        pass

    # Keep track of the total transfer size
    TOTAL_BYTES = 0

    # List the classes
    for rit_class in URLS:
        output(level="Info", message=("Found " + rit_class[1]))

    # Loop through each course
    for course in URLS:

        #
        # Download all files in "content"
        #
        session.get(D2L_BASEURL + "/d2l/le/content/" + course[0] + "/PartialMainView?identifier=TOC&moduleTitle=Table+of+Contents&_d2l_prc%24headingLevel=2&_d2l_prc%24scope=&_d2l_prc%24hasActiveForm=false&isXhr=true&requestId=4")

        toc_page = session.get(D2L_BASEURL + "/d2l/le/content/" + course[0] + "/Home")
        toc_page_soup = BeautifulSoup(toc_page.text, "html.parser")
        toc_page_objs = toc_page_soup.findAll(attrs={'class': 'd2l-collapsepane'})

        # Make the class directory

        output(level="Info", message="Processing " + course[1])
        path = workingDirectory + "/" + course[1].replace("/", ".")    # course[1] is the course code, like NSSA.220

        if not os.path.isdir(safeFilePath(path)):
            output(level="Info", message="Directory does not exist.")
            output(level="Debug", message=safeFilePath(path))
            mkdir_recursive(safeFilePath(path))

        for toc_dataset in toc_page_objs:
            # This is what the folder will be called. I'm replacing the / with a space so we dont get
            pointer = toc_dataset.findAll('h2')[0].text.replace("/", ".")

            tmp_links = toc_dataset.findAll(attrs={'class': 'd2l-link-main'})
            for link in tmp_links:
                try:
                    file_id = link['href'].split('/')[6]
                    url = D2L_BASEURL + "/d2l/le/content/"+ course[0] +"/topics/files/download/" + file_id  + "/DirectFileTopicDownload"
                    path = workingDirectory + "/" + course[1] + "/" + pointer + "/"
                    TOTAL_BYTES += download(url, path)
                except Exception as e:
                    output(level="Error", message="Exception: {}".format(e))
                    continue

        #
        # Download all files in Dropbox
        #
        if course[1] == "PHIL.102.15":
            print(" Edge case I do not want to deal with ")
            continue

        dropbox_resp = session.get(D2L_BASEURL + "/d2l/lms/dropbox/user/folders_list.d2l?ou=" + course[0]  + "&isprv=0")
        dropbox_soup = BeautifulSoup(dropbox_resp.text, "html.parser")

        try:
            dropbox_table = dropbox_soup.find(id='z_b').findAll('tr')
        except AttributeError:
            dropbox_table = []

        if len(dropbox_table) is 1 or len(dropbox_table) is 0:
            output(level="Info", message="No dropbox for {}".format(course[1]))
            continue

        for dropbox_tr in dropbox_table:
            # Get the title of the thing
            if dropbox_tr.text.strip() == "":
                continue

            dropbox_item_title = dropbox_tr.findAll('th', attrs={'class': 'd_ich'})

            if len(dropbox_item_title) == 0:
                continue
            elif dropbox_item_title[0].find('a') is not None and len(dropbox_item_title[0].find('a')) == 1:
                dropbox_item_name = dropbox_item_title[0].find('a').text.replace("/", ".")
            else:
                dropbox_item_name = dropbox_tr.find('label').text.replace("/", ".")

            dropbox_item_page = dropbox_tr.findAll('a')

            WE_GUCCI = False
            for link in dropbox_item_page:
                if "folders_history.d2l" in link['href']:
                    dropbox_item_page = link
                    WE_GUCCI = True

            if not WE_GUCCI:
                continue

            output(level="Info", message="Processing Dropbox for" + safeFilePath(dropbox_item_name))
            dropbox_dl_page = session.get(D2L_BASEURL + dropbox_item_page['href'])
            dropbox_dl_soup = BeautifulSoup(dropbox_dl_page.text, "html.parser")

            # Find all download links
            dropbox_dl_links = dropbox_dl_soup.findAll('span', attrs={'class': 'dfl'})

            for dropbox_dl_link in dropbox_dl_links:
                url = D2L_BASEURL + dropbox_dl_link.find('a')['href']
                path = workingDirectory + "/" + course[1] + "/Dropbox/" + dropbox_item_name + "/"

                TOTAL_BYTES += download(url, path)

            #
            # Download Dropbox Feedback
            #
            output(level="Info", message="Processing Dropbox Feedback for " + safeFilePath(dropbox_item_name))
            feedback_link = dropbox_tr.findAll("a")
            for link in feedback_link:
                if link["href"] is not None and "feedback" in link["href"]:
                    feedback_link = D2L_BASEURL + link["href"]
                    break

            # If we couldn't find a feedback link, then skip
            if type(feedback_link) is str:
                feedback_page = session.get(feedback_link)
                feedback_content = BeautifulSoup(feedback_page.text, "html.parser")
                # Dropboxes can have multiple feedback items, so I need a way to test it.
                # ... Fuck it. I'll just search for the download URL. Make sure we're searching in the feedback page
                feedback_all_links = feedback_content.find("table", {"class": "d_FG"}).findAll("span", {"class": "dfl"})
                for feedback_file in feedback_all_links:
                    feedback_file_url = D2L_BASEURL + feedback_file.find("a")["href"]
                    path = workingDirectory + "/" + course[1] + "/Dropbox_Feedback/" + dropbox_item_name + "/"

                    TOTAL_BYTES += download(feedback_file_url, path)
            else:
                output(level="Info", message="No Feedback")

    MB = TOTAL_BYTES / 1024 / 1024

    output(level="Cool", message="{0}MB Downloaded".format(round(MB, 2)))

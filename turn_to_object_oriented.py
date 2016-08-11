#!/usr/bin/env python
#-*- coding: utf-8 -*-
import csv
import glob
import os
import shutil
import sqlite3
import grequests
import re
from selenium import webdriver

import requests
from tqdm import tqdm
from datetime import datetime, timedelta
import pandas as pd

from Policy import Policy
import Document
from PolicyDocument import PolicyDocument
from Department import Department
from Network import Network
from Connection import Connection
from Date import Date

DATABASE_NAME = "./seoul_documents.db"


def Find_hwp_file_name_and_download_hwp(current_month, doc_list, conn):
    # [ 0: doc_id, 1: row_num, 2: date, 3: title, 4: writer, 5: sender_dep, 6: url, 7: url_for_html_file, 8: url_for_hwp_file, 9: hwp_file_name ]
    #url = 'http://opengov.seoul.go.kr/sanction/8502402'
    print("start requesting original url")
    #session = FuturesSession()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106 Safari/537.36'}
    responses = (grequests.get(doc.url, headers=headers) for doc in doc_list)

    # Cursor for DB
    cursor1 = conn.cursor()

    for response in grequests.map(responses):
        if response != None:
            file_name = re.findall('fid=(.*?)"', response.content.decode("utf-8"))
            # 엑셀문서에 나와있는 날짜가 틀린 경우가 있다. 이런 경우 날짜를 직접 문서상에서 찾아줘야 한다.....
            date_in_doc = re.findall(r'2F[0-9]{8}', response.content.decode("utf-8"))
            url_for_html_file = 'http://opengov.seoul.go.kr/synap/output' + '/' + ''.join(file_name) + '.view.xhtml'
            hwp_file_name = ''.join(file_name) + ".hwp"
            # 그마저도 문서 상에 날짜가 없는 경우에는.. 무시해버린다
            if not date_in_doc:
                date_in_doc.append("0")
            url_for_hwp_file = re.findall("\/sites\/all\/blocks\/download.php\?uri=%2Fdcdata%2F100001%2F[0-9]+%2FF[0-9]+.hwp", response.content.decode())
            if url_for_hwp_file:
                url_for_hwp_file = "http://opengov.seoul.go.kr" + url_for_hwp_file[0]
            else:
                url_for_hwp_file = ""

            url_name = ''.join(re.findall(r'&url=(.*?)\'', response.content.decode("utf-8")))

            for doc in doc_list:
                if str(doc.url) == url_name:
                    doc.url_for_html_file = url_for_html_file
                    doc.url_for_hwp_file = url_for_hwp_file
                    print("url_for_hwp_file is " + url_for_hwp_file)
                    doc.hwp_file_name = hwp_file_name
                    cursor1.execute('update documents_%s SET url_for_html_file=?, url_for_hwp_file=?, hwp_file_name=? \
                                                    where idx=?' % current_month, (doc.url_for_html_file, doc.url_for_hwp_file, doc.hwp_file_name, doc.idx))
                conn.commit()

    print("# of hwp files that will be downloaded: " + str(len(doc_list)))
    # Request hwp file
    for doc in doc_list:
        # url_for_hwp_file이 비어있는 경우를 피한다
        print("url for hwp file is " + doc.url_for_hwp_file)
        if doc.url_for_hwp_file:
            headers = {'Connection': 'close', \
                       'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106 Safari/537.36'}
            # Request timeout가 아닐 경우에만 진행
            try:
                response2 = requests.get(doc.url_for_hwp_file, headers=headers, timeout=15)   # doc_info[9] = url_for_hwp_file
                print("response2 done")
                with open(doc.hwp_file_name, "wb") as handle: # doc_info[10] = hwp_file_name
                    print("start downloading")
                    for data in tqdm(response2.iter_content()):
                        handle.write(data)

                previous_hwp_file_name = doc.hwp_file_name
                new_hwp_file_name = str(doc.idx) + "_" + str(doc.date) + "_" + str(doc.doc_id) + ".hwp"
                # 새 이름을 doc_info[10]에 저장
                doc.hwp_file_name = new_hwp_file_name
                # 새 경로를 지정
                hwp_file_new_path = "/Volumes/Backup/data/hwp_files/hwp_files_%s/" % current_month + new_hwp_file_name
                # 기존 이름(previous_hwp_file_name) => 새 이름(new_hwp_file_name)
                print("New hwp file path is " + hwp_file_new_path)
                print("Previous hwp file name is " + previous_hwp_file_name)
                # hwp 파일이름을 바꾼다
                # hwp파일이 전송된 것이 있을 경우에만 파일이름을 바꾼다
                if previous_hwp_file_name:
                    shutil.move(previous_hwp_file_name, hwp_file_new_path)
                response2.connection.close()
            except requests.exceptions.ConnectionError as e:
                print(e)
            except requests.exceptions.ReadTimeout as e2:
                print(e2)

    return doc_list

### Get document urls associated with a policy
### Input: document_urls (only urls)
### What to do: Get hwp urls from htmls, EXTRACT and save information to DB, and download hwp files
### 기존의 문서데이터와는 다르게 주어진 엑셀파일이 없으므로 직접 전부 정보를 추출해야 한다

def Find_hwp_file_name_and_download_hwp_by_policy(policy, policy_documents_url, conn):
    # [ 0: doc_id, 1: row_num, 2: date, 3: title, 4: writer, 5: sender_dep, 6: url, 7: url_for_html_file, 8: url_for_hwp_file, 9: hwp_file_name ]
    print("start requesting original url")
    response2 = requests.get("http://opengov.seoul.go.kr" + policy_documents_url)
    response_content2 = response2.content.decode()

    # 문서리스트 페이지 돌기
    # 페이지 개수는 (문서 총개수(마지막문서의 인덱스) / 10)의 몫
    last_page_idx = re.findall('(?:"hide-mobile">)([0-9]{,3})(?:</td>)', response_content2)
    # 정책과 관련된 문서가 없어서 인덱스가 없는 경우가 있으므로 체크..
    if last_page_idx:
        print("biggest index is " + last_page_idx[0])
        last_page_idx = (int(last_page_idx[0]) // 15) + 1

        for i in range(last_page_idx):
            response2 = requests.get("http://opengov.seoul.go.kr" + policy_documents_url + "?page=" + str(i))
            response_content2 = response2.content.decode()
            print("Page " + str(i+1) + " of " + policy.id)

            doc_ids = re.findall('(?:"hide-mobile">)([0-9]{,3})(?:</td>)', response_content2)
            titles = re.findall('(?:"tbl-tit">)(.*?)(?:</strong>)', response_content2)
            document_urls = re.findall('(\/sanction\/[0-9]+\?from=policy.*?[0-9]+)(?:"><strong)', response_content2)
            dates = re.findall("[0-9]{4}-[0-9]{2}-[0-9]{2}", response_content2)
            is_publics = re.findall("(?:\"txt-icon tbl-cat\">)([0-9ㄱ-ㅎㅏ-ㅣ가-힣(), ]+)(?:</span>)", response_content2)

            doc_list = []
            # Assign to each PolicyDocument
            for doc_id, title, url, date, is_public in zip(doc_ids, titles, document_urls, dates, is_publics):
                url = "http://opengov.seoul.go.kr" + url
                doc = PolicyDocument("", "", "", "", "", "", "", "", "", "", "", "", "")
                doc.policy_id = policy.id
                doc.doc_id = doc_id
                doc.title = title
                doc.policy_title = policy.title
                doc.date = date
                doc.url = url
                doc.is_public = is_public
                doc_list.append(doc)

            print(document_urls)
            responses = (grequests.get("http://opengov.seoul.go.kr" + document_url) for document_url in document_urls)

            cursor1 = conn.cursor()

            #print "# of requests: " + str(len(grequests.map(responses)))
            # response를 받아서 문서를 추출함과 동시에 doc 객체를 하나 즉석해서 생성해서 정보를 넣는다
            print("just before processing responses")
            for response in grequests.map(responses):
                if response != None:
                    response_content = response.content.decode().replace('\n', '').replace('\t', '')

                    # Get hwp file address
                    file_name = re.findall('fid=(.*?)"', response_content)
                    # 엑셀문서에 나와있는 날짜가 틀린 경우가 있다. 이런 경우 날짜를 직접 문서상에서 찾아줘야 한다.....
                    date_in_doc = re.findall(r'2F[0-9]{8}', response_content)
                    url_for_html_file = 'http://opengov.seoul.go.kr/synap/output' + '/' + ''.join(file_name) + '.view.xhtml'
                    hwp_file_name = ''.join(file_name) + ".hwp"
                    # 그마저도 문서 상에 날짜가 없는 경우에는.. 무시해버린다
                    if not date_in_doc:
                        date_in_doc.append(str(datetime.strptime(doc.date, "%Y-%m-%d") - timedelta(days=1)).replace('00:00:00', '').replace('-', '').replace(' ', ''))

                    url_for_hwp_file = re.findall("\/sites\/all\/blocks\/download.php\?uri=%2Fdcdata%2F100001%2F[0-9]+%2FF[0-9]+.hwp", response.content.decode())
                    if url_for_hwp_file:
                        url_for_hwp_file = "http://opengov.seoul.go.kr" + url_for_hwp_file[0]
                    else:
                        url_for_hwp_file = ""
                    url_name = re.findall(r'(http:\/\/opengov.seoul.go.kr\/sanction\/[0-9]+\?from=policy.*?[0-9]+)', response.content.decode("utf-8"))
                    if url_name:
                        url_name = url_name[0].replace("amp;amp;", "amp;")

                    # Get information from the table in the webpage
                    for doc in doc_list:
                        #print(doc.url)
                        #print(url_name)
                        if doc.url == url_name:
                            doc.writer = re.findall('(?<="accountablePerson">)(.*?)(?=<\/td>)', response_content)[0]
                            doc.sender = re.findall('(?<="contributor">)([^0-9].*?)(?:<)', response_content)[0]
                            doc.url_for_html_file = url_for_html_file
                            doc.url_for_hwp_file = url_for_hwp_file
                            doc.hwp_file_name = hwp_file_name

                            cursor1.execute('INSERT OR REPLACE INTO policy_documents (policy_id, doc_id, title, policy_title, sender, date, writer, \
                                                            url, is_public) \
                                                            values(?,?,?,?,?,?,?,?,?);', (doc.policy_id, doc.doc_id, doc.title, doc.policy_title, doc.sender, doc.date, \
                                                                              doc.writer, doc.url, doc.is_public))

                            break

            conn.commit()


            print("# of hwp files that will be downloaded: " + str(len(doc_list)))
            # Request hwp file
            for doc in doc_list:
                # url_for_hwp_file이 비어있는 경우를 피한다
                print("START downloading " + str(doc.url_for_hwp_file))
                if doc.url_for_hwp_file and (doc.is_public != '비공개'):
                    headers = {'Connection': 'close'}
                    # Request timeout가 아닐 경우에만 진행
                    try:
                        response2 = requests.get(doc.url_for_hwp_file, headers=headers, timeout=15)   # doc_info[9] = url_for_hwp_file
                        with open(doc.hwp_file_name, "wb") as handle: # doc_info[10] = hwp_file_name
                            for data in tqdm(response2.iter_content()):
                                handle.write(data)

                        ### Change the name of hwp folders
                        ### hwp 파일명을 기존 파일명에서 [날짜]_[id] 로 바꾼다

                        previous_hwp_file_name = doc.hwp_file_name
                        new_hwp_file_name = str(doc.policy_id) + "_" + str(doc.doc_id) + "_" + str(doc.date.replace('-','')) + ".hwp"
                        # 새 이름을 doc_info[10]에 저장
                        doc.hwp_file_name = new_hwp_file_name
                        # 새 경로를 지정
                        hwp_file_new_path = "./data/hwp_files/hwp_files_by_policy/" + new_hwp_file_name
                        # 기존 이름(previous_hwp_file_name) => 새 이름(new_hwp_file_name)
                        print("New hwp file path is " + hwp_file_new_path)
                        print("Previous hwp file name is " + previous_hwp_file_name)
                        # hwp 파일이름을 바꾼다
                        # hwp파일이 전송된 것이 있을 경우에만 파일이름을 바꾼다
                        if previous_hwp_file_name:
                            os.rename(previous_hwp_file_name, hwp_file_new_path)
                        print("FINISH downloading " + doc.url_for_hwp_file)
                        response2.connection.close()
                    except requests.exceptions.ConnectionError as e:
                        print(e)
                    except requests.exceptions.ReadTimeout as e2:
                        print(e2)

def Find_hwp_file_name_and_download_hwp_by_search_for_policy(policy, conn):
    # 검색페이지 연결 - 키워드 주입, 기간도 함께 주입
    # 키워드가 여러개면 루프 돌기(e.g., 세빛섬+공공성,공공성확보심의위원회,세빛섬+공공성확보)
    print("Current policy id is " + policy.id)
    for keyword in policy.keyword.split(","):
        keyword = keyword.replace("\n", "")
        print(keyword)
        doc_url = "http://opengov.seoul.go.kr/sanction?&startDate=%s&endDate=%s" % (policy.date.from_date, policy.date.to_date)
        for keyword_token in keyword.split("+"):
            url_for_keyword = "&searchField%" + "5B%" + "5D=TITLE&searchFieldOpt%" + "5B%" + "5D=%" + "3A&searchFieldKeyword%" + "5B%" + "5D=%s" % keyword_token
            doc_url += url_for_keyword
        response = requests.get(doc_url)
        print(doc_url)
        response_content = response.content.decode()
        cursor3 = conn.cursor()

        # 문서리스트 페이지 돌기
        # 페이지 개수는 (문서 총개수(마지막문서의 인덱스) / 10)의 몫
        last_page_idx = re.findall('(?:"hide-mobile">)([0-9]{,3})(?:</td>)', response_content)
        # 정책과 관련된 문서가 없어서 인덱스가 없는 경우가 있으므로 체크..
        if last_page_idx:
            print("biggest index is " + last_page_idx[0])
            last_page_idx = (int(last_page_idx[0]) // 15) + 1

            for i in range(last_page_idx):
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106 Safari/537.36'}
                    response2 = requests.get("http://opengov.seoul.go.kr/sanction" + "?page=" + str(i) + doc_url.replace("http://opengov.seoul.go.kr/sanction",""), headers=headers)
                    print("http://opengov.seoul.go.kr/sanction" + "?page=" + str(i) + doc_url.replace("http://opengov.seoul.go.kr/sanction",""))
                    response_content2 = response2.content.decode().replace('\n', '').replace('\t', '')
                    print("Page " + str(i+1) + " of " + policy.id)

                    doc_ids = re.findall('(?:\/sanction\/)([0-9]+)(?:\"><strong)', response_content2)
                    titles = [ title.replace("<em class=\"search-highlight\">","").replace("</em>","") for title in re.findall('(?:"tbl-tit">)(.*?)(?:</strong>)', response_content2) ]
                    document_urls = re.findall("(\/sanction\/[0-9]+)(?:\"><strong)", response_content2)
                    dates = re.findall('(?:"hide-mobile">)([0-9]{4}-[0-9]{2}-[0-9]{2})(?:</td>)', response_content2)
                    is_publics = re.findall("(?:\"txt-icon tbl-cat\">)([0-9ㄱ-ㅎㅏ-ㅣ가-힣(), ]+)(?:</span>)", response_content2)

                    print(doc_ids)
                    print(document_urls)
                except requests.exceptions.ConnectionError as e:
                    print(e)
                except requests.exceptions.ReadTimeout as e2:
                    print(e2)

                doc_list = []
                # Assign to each PolicyDocument
                for doc_id, title, url, date, is_public in zip(doc_ids, titles, document_urls, dates, is_publics):
                    # 이미 DB에 들어가 있는 정책문서와 중복되는 문서라면 url로 걸러낸다
                    policy_doc = PolicyDocument("", "", "", "", "", "", "", "", "", "", "", "", "")
                    if url not in policy_doc.get_policy_urls_by_policy_id(cursor3):
                        print('{} {} {}'.format(doc_id, title, url, date, is_public))
                        url = "http://opengov.seoul.go.kr" + url
                        policy_doc.policy_id = policy.id
                        policy_doc.doc_id = int(doc_id)  # 검색에 의한 문서들은 10000번대부터 시작
                        policy_doc.title = title
                        policy_doc.policy_title = policy.title
                        policy_doc.date = date
                        policy_doc.url = url
                        policy_doc.is_public = is_public
                        doc_list.append(policy_doc)
                        print(policy_doc.doc_id, policy_doc.policy_id, policy_doc.url)

                headers = {'User-agent': 'Googlebot/2.1'}
                responses = (grequests.get("http://opengov.seoul.go.kr" + document_url, headers=headers) for document_url in document_urls)

                cursor1 = conn.cursor()

                # response를 받아서 문서를 추출함과 동시에 doc 객체를 하나 즉석해서 생성해서 정보를 넣는다
                print("just before processing responses")
                for response in grequests.map(responses):
                    if response != None:
                        response_content = response.content.decode().replace('\n', '').replace('\t', '')
                        # Get hwp file address
                        file_name = re.findall('fid=(.*?)"', response_content)
                        # 엑셀문서에 나와있는 날짜가 틀린 경우가 있다. 이런 경우 날짜를 직접 문서상에서 찾아줘야 한다.....
                        date_in_doc = re.findall(r'2F[0-9]{8}', response_content)
                        url_for_html_file = 'http://opengov.seoul.go.kr/synap/output' + '/' + ''.join(file_name) + '.view.xhtml'
                        hwp_file_name = ''.join(file_name) + ".hwp"
                        url_for_hwp_file = re.findall("\/sites\/all\/blocks\/download.php\?uri=%2Fdcdata%2F100001%2F[0-9]+%2FF[0-9]+.hwp", response_content)
                        if url_for_hwp_file:
                            url_for_hwp_file = "http://opengov.seoul.go.kr" + url_for_hwp_file[0]
                        else:
                            url_for_hwp_file = ""

                        url_names = re.findall('(http:\/\/opengov.seoul.go.kr\/sanction\/[0-9]+)', response_content)
                        if url_names:
                            url_name = url_names[0]
                        else:
                            url_name = ""


                        # Get information from the table in the webpage
                        for policy_doc in doc_list:
                            if policy_doc.url == url_name:
                                policy_doc.writer = re.findall('(?<="accountablePerson">)(.*?)(?=<\/td>)', response_content)[0]
                                policy_doc.sender = ''.join(re.findall('(?<="contributor">)([^0-9].*?)(?:<)', response_content))
                                policy_doc.url_for_html_file = url_for_html_file
                                policy_doc.url_for_hwp_file = url_for_hwp_file
                                policy_doc.hwp_file_name = hwp_file_name

                                policy_doc.insert_relevant_doc_info_by_policy(cursor1)
                                break

                conn.commit()


                print("# of hwp files that will be downloaded: " + str(len(doc_list)))
                # Request hwp file
                for doc in doc_list:
                    # url_for_hwp_file이 비어있는 경우를 피한다
                    print("START downloading " + str(doc.url_for_hwp_file))
                    if doc.url_for_hwp_file and (doc.is_public != '비공개'):
                        headers = {'User-Agent':'Mozilla/5.0 (Windows; U; Windows NT 5.1; it; rv:1.8.1.11) Gecko/20071127 Firefox/2.0.0.11', \
                                   'Connection': 'Close'}
                        # Request timeout가 아닐 경우에만 진행
                        try:
                            response2 = requests.get(doc.url_for_hwp_file, headers=headers, timeout=15)   # doc_info[9] = url_for_hwp_file
                            with open(doc.hwp_file_name, "wb") as handle: # doc_info[10] = hwp_file_name
                                for data in tqdm(response2.iter_content()):
                                    handle.write(data)

                            ### Change the name of hwp folders
                            ### hwp 파일명을 기존 파일명에서 [날짜]_[id] 로 바꾼다


                            previous_hwp_file_name = doc.hwp_file_name
                            scriptpath = os.path.dirname(__file__)
                            previous_hwp_file_name = os.path.join(scriptpath, previous_hwp_file_name)

                            new_hwp_file_name = str(doc.policy_id) + "_" + str(doc.doc_id) + "_" + str(doc.date.replace('-','')) + ".hwp"
                            # 새 이름을 doc_info[10]에 저장
                            doc.hwp_file_name = new_hwp_file_name
                            # 새 경로를 지정
                            hwp_file_new_path = "/Volumes/Backup/data/hwp_files/hwp_files_by_policy/" + new_hwp_file_name
                            # 기존 이름(previous_hwp_file_name) => 새 이름(new_hwp_file_name)
                            print("New hwp file path is " + hwp_file_new_path)
                            print("Previous hwp file name is " + previous_hwp_file_name)
                            # hwp 파일이름을 바꾼다
                            # hwp파일이 전송된 것이 있을 경우에만 파일이름을 바꾼다
                            if not os.path.exists(hwp_file_new_path):
                                shutil.move(previous_hwp_file_name, hwp_file_new_path)
                            print("FINISH downloading " + doc.url_for_hwp_file)
                            response2.connection.close()
                        except requests.exceptions.ConnectionError as e:
                            print(e)
                        except requests.exceptions.ReadTimeout as e2:
                            print(e2)

def Extract_hwp_sources_and_find_receivers_by_month(txt_file_name):
    #############
    ###### ./txt_files 안에서 작업 중
    #############

    print(txt_file_name)
    # txt 파일이 있는 경로를 지정한다
    file = open(txt_file_name, "r")
    #txt 파일로부터 hwp 소스코드를 읽어낸다
    hwp_code = file.read()

    doc_id = re.findall(r'([0-9]+)(?:_)', txt_file_name)[0]
    print(doc_id)

    receiver_text = re.findall(r'[0-9ㄱ-ㅎㅏ-ㅣ가-힣(), ]+</CHAR>', hwp_code)
    receiver_text = ''.join(receiver_text)

    if '수신' in receiver_text: # or (receiver_text.find(u'수신') != -1):   # !!!!!!!!! 수 신 자 도 잡아내자
        receiver_text = receiver_text[(receiver_text.index('수신')+len('수신')):]
        # 수신자 단어 외에 '수신자 참조'라는 단어가 있어서 '수신자'가 제대로 잡히지 않은 경우, 다시 한번 잡아낸다
        if '수신자' in receiver_text:
            receiver_text = receiver_text[(receiver_text.index('수신자')+len('수신자')):]
        # '수신자참조'가 있는 경우, 문서 하단에 수신자가 나열되어 있는 경우가 있다. 그러므로 '수신자' 단어를 다시 한번 잡아내야 한다
        if '수신자' in receiver_text:
            receiver_text = receiver_text[(receiver_text.index('수신자')+len('수신자')):]
        # 두번째 등장하는 </span>까지 자르면 수신자 목록만 남게 된다
        try:
            span_index = receiver_text.index('</CHAR>')
            span_index2 = receiver_text.index('</CHAR>', receiver_text.index('</CHAR>')+1)
            # 마침내 수신자 목록을 얻었다..하....
            receiver = receiver_text[span_index + len('</CHAR>'):span_index2]
            # 공백이 있는 경우 제거하기
            receiver = receiver.replace(" ", "")
            # match = hangul.search(receiver_text)
            # print receiver_text[match.start():match.end()]
            print("receiver: " + receiver)

            return (doc_id, receiver)
        except:
            receiver = "No receiver"
            print("No receiver")
            return (doc_id, receiver)
    else:
        receiver = "No receiver"
        print("No receiver")
        return (doc_id, receiver)

def Extract_hwp_sources_and_find_receivers_for_policy(txt_file_name):
    #############
    ###### ./txt_files 안에서 작업 중
    #############

    print(txt_file_name)
    # txt 파일이 있는 경로를 지정한다
    file = open(txt_file_name, "r")
    #txt 파일로부터 hwp 소스코드를 읽어낸다
    hwp_code = file.read()

    policy_id = ''.join(re.findall(r'([0-9]+-[0-9]+)(?:_)', txt_file_name))
    doc_id = ''.join(re.findall(r'(?:_)([0-9]+)(?:_)', txt_file_name))

    receiver_text = [ text.replace(" ","") for text in re.findall('(?:<CHAR>)(.*?)(?:</CHAR>)', hwp_code) ]

    if "수신" in receiver_text:
        if "수신자참조" in receiver_text:
            if "수신자" in receiver_text:
                receiver_index = receiver_text.index("수신자") + 1
                receiver = receiver_text[receiver_index]
            else:
                receiver = "No receiver"
        else:
            if "수신" in receiver_text:
                receiver_index = receiver_text.index("수신") + 1
                receiver = receiver_text[receiver_index]
            else:
                receiver = "No receiver"
    else:
        receiver = "No receiver"

    print("receiver: " + receiver)
    return (policy_id, doc_id, receiver)


def main():
    option = input("Select menu: ")
    conn = sqlite3.connect(DATABASE_NAME)
    connection = Connection("", "", "", "")

    if option == "1":
        current_month = input("Enter a month (e.g., 201501) : ")
        start_idx = int(input("Enter the start index : "))

        end_idx = 0
        range_idx = 75

        doc_list = []

        for i in range(1, 11001):
            end_idx = start_idx + range_idx
            print("End index is " + str(end_idx))
            doc_list.clear()

            cursor = conn.cursor()
            rows = cursor.execute("select * from documents_" + current_month)

            for doc_idx, doc_info in enumerate(rows):
                if start_idx < doc_idx <= end_idx:
                    #print(doc_info[6])
                    doc = Document.Document("", "", "", "", "", "", "", "", "", "", "", "")
                    doc.filter_and_insert_doc_info_to_DB(doc_info)
                    doc_list.append(doc)

            start_idx = end_idx

            Find_hwp_file_name_and_download_hwp(current_month, doc_list, conn)
    if option == '2':
        current_month = input("Enter a month (e.g., 201501, or \'by_policy\' for policy) : ")
        start = int(input("Enter the start index : "))

        end = 0
        range_idx = 30

        # node script를 통해 hwp파일을 txt파일로 변환한다
        for i in range(1, 3000):
            end = start + range_idx
            print("End index is " + str(end))
            os.system("INDEX1=%s INDEX2=%d INDEX3=%d node ./node_hwp_test/test.js" % (current_month, start, end))
            start = end

    if option == '4':
        connections = connection.get_senders_and_receivers_by_month(1, 1)

    if option == '5':
        connections = connection.get_senders_and_receivers_by_month(1, 1)
        connection.count_connections(connections)
        # for connection in connections:
        #    print(connection.sender, connection.receiver)

    if option == '6':
        # Write csv file
        connection.write_connections_to_csv("connections.csv", connections)

    if option == '7':
        print("한달씩 입력해야 한다. (1월을 출력하고 싶다면, 2015-01 , 2015-02를 입력.")
        from_month = input("Enter a starting month (e.g., 2015-01) : ")
        to_month = input("Enter a ending month (e.g., 2016-04) : ")

        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()

        connections = connection.get_senders_and_receivers_by_month(from_month, to_month)
        connection.count_connections(connections)
        counted_connections_dict = connection.count_connections(connections)
        filtered_connections_dict = department.verify_dep_names(counted_connections_dict, depts_list,
                                                                towns_list)
        department.write_csv_for_gephi(depts_list, filtered_connections_dict, "edges_list_%s.csv" % from_month.replace("-", ""))


    if option == '8':
        # argument: idx, work_category, title, sender, receiver
        document = Document.Document("", "", "", "", "")
        documents = document.get_doc_info(1, 1)
        document.write_results_to_txt("doc_info_201501.txt", documents)

    if option == '9':
        department = Department("")
        depts_list = department.get_all_departments("seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers_by_month(1, 1)
        counted_connections_dict = connection.count_connections(connections)
        filtered_connections_dict = department.verify_dep_names(counted_connections_dict, depts_list,
                                                                              towns_list)
        department.write_csv_for_gephi(depts_list, filtered_connections_dict, "edges_list_201501.csv")

    if option == '10':
        document = Document.Document()
        document.count_documents_by_condition()


##### From here #######
### 정책관련문서 메뉴들 ###
#######################

    if option == "11":
        for i in range(18):
            response = requests.get(
                "http://opengov.seoul.go.kr/policy?field_policy_year_value=All&search=&items_per_page=15&page=%d&policy_year=All&policy_done=All" % i)

            cursor = conn.cursor()
            cursor2 = conn.cursor()

            # 이미 저장된 정책들은 다시 방문하지 않는다
            cursor.execute("select policy_id, doc_id from policy_documents")
            completed_policy_ids = set([result[0] for result in set(list(cursor.fetchall())) if
                                    (result[1] == 1) or (result[1] == 2) or (result[1] == 3)])  # 정책문서의 끝까지 다 저장된 경우만 따진다
            print(completed_policy_ids)

            policy_urls = re.findall('\/policy\/project\/[0-9]+', response.content.decode())  # 정책 url
            policy_urls = set(policy_urls)
            print("here")
            # 정책 리스트 한 페이지 내에 있는 정책 loop
            for policy_url in policy_urls:
                response2 = requests.get("http://opengov.seoul.go.kr" + policy_url)  # Project information page
                response2_content = response2.content.decode().replace('\n', '').replace('\t', '')

                policy = Policy("", "", "", "", "", "", "", "", "", "")

                print("Starting this policy url: " + "http://opengov.seoul.go.kr" + policy_url)
                policy.id = re.findall('(?:사업번호</th><td>)([0-9-]+)(?:<)', response2_content)[0]
                policy.title = re.findall('(?:정책명</th><td>)(.*?)(?:<)', response2_content)[0]
                print("policy title is " + ''.join(policy.title))
                policy.area = re.findall('(?:분야</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.period = re.findall('(?:기간</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.is_public = re.findall('(?:공개구분</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.department = re.findall('(?:담당부서</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.writer = re.findall('(?:담당자</th><td>)(.*?)(?:<)', response2_content)[0]

                if policy.is_public == '공개':
                    policy.is_public = 1
                else:
                    policy.is_public = 0

                print(policy.id, policy.title, policy.area, policy.period, policy.is_public, policy.department,
                      policy.writer)

                # policy.insert_policy_info_to_DB(cursor)

                if policy.id not in completed_policy_ids:
                    policy_documents_url = re.findall('\/policy\/list\/[0-9]+', response2_content)[
                        0]  # document list page for policy
                    Find_hwp_file_name_and_download_hwp_by_policy(policy, policy_documents_url, conn)

            conn.commit()

    if option == '12':
        cursor2 = conn.cursor()
        # Open text files and extract receivers from hwp codes
        # Get receivers and write them to excel file
        for txt_file_name in glob.glob("/Volumes/Backup/data/txt_files/txt_files_by_policy/*.txt"):
            if Extract_hwp_sources_and_find_receivers_for_policy(txt_file_name) != None:
                (policy_id, doc_id, receiver) = Extract_hwp_sources_and_find_receivers_for_policy(txt_file_name)
                # 입력할 셀의 인덱스를 만든다(L => 13번째 컬럼)
                cursor2.execute('update policy_documents SET receiver=? \
                                                        where policy_id=? and doc_id=?', (receiver, policy_id, doc_id))

        conn.commit()
        conn.close()

    if option == '14':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers_by_policy_and_date()
        connection.count_connections(connections)

        filtered_connections_dict = department.verify_dep_names_from_txt_file_by_policy_and_date("./data/edges_for_policy.txt", depts_list,
                                                                              towns_list)
        department.write_csv_for_gephi(depts_list, filtered_connections_dict, "./data/edges_list_for_policy.csv")

    if option == '15':
        connections = connection.get_senders_and_receivers_by_month(1, 1)
        connection.count_connections(connections)

    ### 31. 일반문서로부터 정책키워드로 정책과 관련된 일반문서 가져오기
    if option == '31':
        doc = Document.Document("", "", "", "", "", "", "", "", "", "", "", "")
        policy_doc = PolicyDocument("", "", "", "", "", "", "", "", "", "", "", "", "")

        cursor = conn.cursor()
        cursor2 = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor2.row_factory = sqlite3.Row
        cursor.execute("select * from policy")

        policies = []

        for row in cursor:
            policy = Policy("", "", "", "", "", "", "", "", "", "")
            # 정책객체 초기화
            policy.id = row["id"]
            policy.title = row["title"]
            print("Current policy is " + policy.id)
            policy.keyword = row["keyword"]
            policy.date = Date("", "")
            print("Policy period is " + row["period"])
            (policy.date.from_date, policy.date.to_date) = policy.date.format_date(row["period"])
            policy.date.from_date = policy.date.set_range_of_from_date(policy.date.from_date, "2015-01-01", "2016-04-30")
            policy.date.to_date = policy.date.set_range_of_to_date(policy.date.to_date, "2015-01-01", "2016-04-30")
            print("Updated Policy period is " + policy.date.from_date + ", " + policy.date.to_date)

            # 정책기간이 2015.1.1 ~ 2016.4.30에서 벗어나면 분석하지 않는다
            if (policy.date.from_date != "Invalid") and (policy.date.to_date != "Invalid"):
                doc.get_doc_info_by_policy_keywords(policy, conn)

    # 32. 서울시 홈페이지 검색을 통해 정책관련문서 검색하기
    if option == '32':
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("select * from policy")
        done_list = ['2014-65', '2014-66', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-56', '2014-63', '2014-49', '2014-65', '2014-59', '2014-52', '2014-51', '2014-55', '2015-43', '2015-49', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2014-3', '2014-8', '2014-15', '2014-9', '2014-16', '2014-7', '2014-6', '2014-5', '2014-14', '2014-12', '2013-29', '2013-28', '2013-31', '2013-32', '2013-33', '2013-34', '2014-1', '2013-27', '2013-35', '2013-25', '2013-30', '2013-36', '2013-39', '2013-26', '2013-37', '2013-10', '2013-22', '2013-8', '2013-13', '2013-7', '2013-9', '2013-23', '2013-17', '2013-15', '2013-24', '2013-18', '2013-14', '2013-11', '2013-19', '2013-5', '2013-1', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2014-3', '2014-8', '2014-15', '2014-9', '2014-16', '2014-7', '2014-6', '2014-5', '2014-14', '2014-12', '2013-29', '2013-28', '2013-31', '2013-32', '2013-33', '2013-34', '2014-1', '2013-27', '2013-35', '2013-25', '2013-30', '2013-36', '2013-39', '2013-26', '2013-37', '2013-10', '2013-22', '2013-8', '2013-13', '2013-7', '2013-9', '2013-23', '2013-17', '2013-15', '2013-24', '2013-18', '2013-14', '2013-11', '2013-19', '2013-5', '2013-1', '2013-3', '2012-39', '2012-41', '2012-47', '2012-42', '2012-49', '2012-50', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2014-3', '2014-8', '2014-15', '2014-9', '2014-16', '2014-7', '2014-6', '2014-5', '2014-14', '2014-12', '2013-29', '2013-28', '2013-31', '2013-32', '2013-33', '2013-34', '2014-1', '2013-27', '2013-35', '2013-25', '2013-30', '2013-36', '2013-39', '2013-26', '2013-37', '2013-10', '2013-22', '2013-8', '2013-13', '2013-7', '2013-9', '2013-23', '2013-17', '2013-15', '2013-24', '2013-18', '2013-14', '2013-11', '2013-19', '2013-5', '2013-1', '2013-3', '2012-50', '2013-2', '2012-35', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2014-3', '2014-8', '2014-15', '2014-9', '2014-16', '2014-7', '2014-6', '2014-5', '2014-14', '2014-12', '2013-29', '2013-28', '2013-31', '2013-32', '2013-33', '2013-34', '2014-1', '2013-27', '2013-35', '2013-25', '2013-30', '2013-36', '2013-39', '2013-26', '2013-37', '2013-10', '2013-22', '2013-8', '2013-13', '2013-7', '2013-9', '2013-23', '2013-17', '2013-15', '2013-24', '2013-18', '2013-14', '2013-11', '2013-19', '2013-5', '2013-1', '2013-3', '2012-50', '2013-2', '2012-35', '2012-49', '2012-48', '2012-42', '2012-41', '2012-43', '2012-47', '2012-39', '2012-38', '2012-34', '2012-36', '2012-28', '2012-12', '2012-31', '2012-30', '2012-11', '2012-15', '2012-2', '2012-33', '2012-5', '2012-6', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2014-3', '2014-8', '2014-15', '2014-9', '2014-16', '2014-7', '2014-6', '2014-5', '2014-14', '2014-12', '2013-29', '2013-28', '2013-31', '2013-32', '2013-33', '2013-34', '2014-1', '2013-27', '2013-35', '2013-25', '2013-30', '2013-36', '2013-39', '2013-26', '2013-37', '2013-10', '2013-22', '2013-8', '2013-13', '2013-7', '2013-9', '2013-23', '2013-17', '2013-15', '2013-24', '2013-18', '2013-14', '2013-11', '2013-19', '2013-5', '2013-1', '2013-3', '2012-50', '2013-2', '2012-35', '2012-49', '2012-48', '2012-42', '2012-41', '2012-43', '2012-47', '2012-39', '2012-38', '2012-34', '2012-36', '2012-28', '2012-12', '2012-31', '2012-30', '2012-11', '2012-15', '2012-2', '2012-33', '2012-5', '2012-6', '2012-7', '2012-10', '2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2014-3', '2014-8', '2014-15', '2014-9', '2014-16', '2014-7', '2014-6', '2014-5', '2014-14', '2014-12', '2013-29', '2013-28', '2013-31', '2013-32', '2013-33', '2013-34', '2014-1', '2013-27', '2013-35', '2013-25', '2013-30', '2013-36', '2013-39', '2013-26', '2013-37', '2013-10', '2013-22', '2013-8', '2013-13', '2013-7', '2013-9', '2013-23', '2013-17', '2013-15', '2013-24', '2013-18', '2013-14', '2013-11', '2013-19', '2013-5', '2013-1', '2013-3', '2012-50', '2013-2', '2012-35', '2012-49', '2012-48', '2012-42', '2012-41', '2012-43', '2012-47', '2012-39', '2012-38', '2012-34', '2012-36', '2012-28', '2012-12', '2012-31', '2012-30', '2012-11', '2012-15', '2012-2', '2012-33', '2012-5', '2012-6', '2012-7', '2012-10', '2012-23', '2012-13', '2012-4', '2011-114', '2011-111', '2011-97', '2011-96', '2011-107', '2011-104', '2011-112', '2011-115', '2011-105', '2011-100', '2011-103', '2011-108', '2011-119', '2011-106', '2011-122', '2011-89', '2011-86', '2011-80', '2011-77', '2011-81', '2011-94', '2011-93', '2011-85', '2011-92', '2011-87', '2011-78', '2011-79', '2011-83', '2011-82', '2011-88', '2011-59', '2011-53', '2011-71', '2011-55']

        for row in cursor:
            policy = Policy("", "", "", "", "", "", "", "", "", "")
            # 정책객체 초기화
            policy.id = row["id"]
            policy.keyword = row["keyword"]
            policy.title = row["title"]
            policy.date = Date("", "")
            print("Previous policy period is " + row["period"])
            (policy.date.from_date, policy.date.to_date) = policy.date.format_date(row["period"])
            policy.date.from_date = policy.date.set_range_of_from_date(policy.date.from_date, "2011-01-01", "2016-07-31")
            policy.date.to_date = policy.date.set_range_of_to_date(policy.date.to_date, "2011-01-01", "2016-07-31")
            print("Updated Policy period is " + policy.date.from_date + ", " + policy.date.to_date)

            if policy.id not in done_list:
                Find_hwp_file_name_and_download_hwp_by_search_for_policy(policy, conn)
            done_list.append(policy.id)
            print("Done list is: " + str(done_list))

    if option == '41':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy_and_date(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list,
            towns_list)

        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            month = key1[1]
            policy_title = key1[2]
            network = None
            network = Network(edges)
            network.draw_policy_graph_by_month(policy_id, month, policy_title)

    if option == '42':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list,
                                                                             towns_list)

        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_title = key1[1]
            network = None
            network = Network(edges)
            network.make_whole_policy_graph(policy_id, policy_title)

    if option == '51':
        for i in range(18):
            response = requests.get(
                "http://opengov.seoul.go.kr/policy?field_policy_year_value=All&search=&items_per_page=15&page=%d&policy_year=All&policy_done=All" % i)

            cursor = conn.cursor()

            # 이미 저장된 정책들은 다시 방문하지 않는다
            cursor.execute("select id from policy")
            completed_policy_ids = set(list(cursor.fetchall()))
            print(completed_policy_ids)

            policy_urls = re.findall('\/policy\/project\/[0-9]+', response.content.decode())  # 정책 url
            policy_urls = set(policy_urls)
            # 정책 리스트 한 페이지 내에 있는 정책 loop
            for policy_url in policy_urls:
                response2 = requests.get("http://opengov.seoul.go.kr" + policy_url)  # Project information page
                response2_content = response2.content.decode().replace('\n', '').replace('\t', '')

                policy = Policy("", "", "", "", "", "", "", "", "", "")

                print("Starting this policy url: " + "http://opengov.seoul.go.kr" + policy_url)
                policy.id = re.findall('(?:사업번호</th><td>)([0-9-]+)(?:<)', response2_content)[0]
                policy.title = re.findall('(?:정책명</th><td>)(.*?)(?:<)', response2_content)[0]
                print("policy title is " + ''.join(policy.title))
                policy.area = re.findall('(?:분야</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.period = re.findall('(?:기간</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.is_public = re.findall('(?:공개구분</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.department = re.findall('(?:담당부서</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.writer = re.findall('(?:담당자</th><td>)(.*?)(?:<)', response2_content)[0]
                policy.budget = re.findall('(?:소요예산</th><td>)(.*?)(?:<)', response2_content)[0]

                if policy.is_public == '공개':
                    policy.is_public = 1
                else:
                    policy.is_public = 0

                print(policy.id, policy.title, policy.area, policy.period, policy.is_public, policy.department,
                      policy.writer, policy.budget)

                policy.insert_policy_info_to_DB(cursor)

            conn.commit()
        conn.close()

    if option == '52':
        print("수신자를 추출하고 싶은 기간을 입력하세요")
        from_month = input("YYYY-MM 부터:")
        to_month = input("YYYY-MM 까지:")
        cursor2 = conn.cursor()
        # Open text files and extract receivers from hwp codes
        # Get receivers and write them to excel file

        from_date = datetime(int(from_month.split('-')[0]), int(from_month.split('-')[1]), 1)
        to_date = datetime(int(to_month.split('-')[0]), int(to_month.split('-')[1]), 2)
        date_dict = pd.DataFrame(pd.date_range(from_date, to_date, freq='M'))

        for idx, date in date_dict.items():
            months = [month.replace('-', '') for month in re.findall('[0-9]{4}-[0-9]{2}', str(date))]
            for current_month in months:
                for txt_file_name in glob.glob("/Volumes/Backup/data/txt_files/txt_files_%s/*.txt" % current_month):
                    if Extract_hwp_sources_and_find_receivers_by_month(txt_file_name) != None:
                        (id, receiver) = Extract_hwp_sources_and_find_receivers_by_month(txt_file_name)
                        # 입력할 셀의 인덱스를 만든다(L => 13번째 컬럼)
                        cursor2.execute('update documents_%s SET receiver=? \
                                                                    where idx=?' % current_month, (receiver, id))

                    conn.commit()
        conn.close()
    if option == '56':
        cursor = conn.cursor()
        # 정책키워드...
        file = open("./data/policy_keywords.txt", "r")
        rows = file.readlines()
        for row in rows:
            policy_id = row.split("\t")[0]
            keywords = row.split("\t")[1]
            print(policy_id, keywords)
            cursor.execute("update policy SET keyword=? where id=?", (keywords, policy_id))

        conn.commit()

    if option == '57':
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row


        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list,
                                                                             towns_list)

        with open('policy_data.csv', 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=",")
            print(len(filtered_edges_dict.items()))
            for key, edges in filtered_edges_dict.items():
                #print(key1[0])
                policy_id = key[0]
                policy_dept = key[1]
                policy_title = key[2]
                network = Network(edges)
                centralization_score = network.calculate_centralization_of_policy_graph(policy_id, policy_title)
                nodes_centrality_dict = network.calculate_centrality_of_policy_graph(policy_id, policy_title)
                cursor.execute("select * from policy")
                for row in cursor:
                    if policy_id == row["id"]:
                        if policy_dept in nodes_centrality_dict.keys():
                            centrality = nodes_centrality_dict[policy_dept]
                            print(row["id"], row["title"], policy_dept, "{0:.2f}".format(centralization_score), \
                                                "{0:.2f}".format(centrality), row["budget"], row["area"])
                        # 이름이 정확히 일치하는 부서가 없다면,
                        else:
                            # Just capture the department with the maximum centrality
                            policy_dept = max(nodes_centrality_dict, key=nodes_centrality_dict.get)
                            centrality = nodes_centrality_dict[policy_dept]
                            print(row["id"], row["title"], policy_dept, "{0:.2f}".format(centralization_score), \
                                  "{0:.2f}".format(centrality), row["budget"], row["area"])

                        writer.writerow([row["id"], row["title"], policy_dept, "{0:.2f}".format(centralization_score), \
                             "{0:.2f}".format(centrality), row["budget"], row["area"]])


        conn.commit()
        conn.close()

    if option == '61':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list,
                                                                             towns_list)
        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_title = key1[1]
            network = None
            network = Network(edges)
            network.calculate_centralization_of_policy_graph(policy_id, policy_title)

    if option == '62':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list,
                                                                             towns_list)
        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_title = key1[1]
            network = None
            network = Network(edges)
            network.calculate_centrality_of_policy_graph(policy_id, policy_title)

    if option == '99':
        txt_file_path = "/Volumes/Backup/data/txt_files/txt_files_by_policy/2011-36_1304270_20140417.txt"

        result = Extract_hwp_sources_and_find_receivers_for_policy(txt_file_path)
        print(result)

def menu():

    print(
        "그룹 1. 일반문서 크롤링 \n" \
        "\t 1. 일반문서 크롤링 : 원하는 기간 선택, DB에 정보 저장, 한글파일 다운로드 \n" \
        "\t 2. txt 파일로 변환 \n" \
        "\t 4. DB로부터 송수신자 받아서 출력하기\n" \
        "\t 5. 송수신자 종류별로 주고받은 문서개수 세고 딕셔너리에 저장하기\n" \
        "\t 6. Gephi: 송수신자 정보 csv에 출력하기\n" \
        "\t 7. Gephi: 송수신자 정보를 월별로 csv에 출력하기\n" \
        "\t 8. 문서 정보 txt에 출력하기\n" \
        "\t 9. 서울시 내부부서만 가려내서 출력하기\n"
        "\t 10. 조건에 맞는 문서개수 파악하기\n"

        "그룹 2. 정책관련문서 크롤링 \n" \
        "\t 11. 정책관련문서 크롤링 : \n" \
        "\t 12. 정책관련문서 수신자정보 추출 \n" \
        "\t 14. DB로부터 송수신자 받고 -> 외부기관 제외 & 송수신자 일대일로 처리\n" \
        "\t 15. 송수신자 종류별로 주고받은 문서개수 세고 딕셔너리에 저장하기\n" \

        "그룹 3. 일반문서로부터 정책 키워드로 크롤링 \n"\
        "\t 31. 일반문서로부터 정책키워드로 정책과 관련된 일반문서 가져오기 \n" \
        "\t 32. 서울시 홈페이지 검색을 통해 정책관련문서 검색하기 \n"\

        "그룹 4. 네트워크 시각화 \n" \
        "\t 41. 정책문서 시각화 \n" \

        "그룹 5. DB queries \n" \
        "\t 51. Insert: 정책 데이터 저장 \n" \
        "\t 52. Insert: 월별 수신자 정보 추출 from txt files & 저장\n"\
        "\t 53. Update: 정책 키워드 입력하기"
        "\t 56. Select: 일반문서 데이터를 정책 키워드로 검색하여 정책관련문서 추리기 \n" \
        "\t 57. Select: 정책별 사업번호, 사업명, 주무부서 and centralization, centrality of primary department -> csv로 출력 \n" \
 \
        "그룹 6. 네트워크 속성 \n" \
        "\t 61. 정책별 네트워크 + centralization  \n" \
        "\t 61. 정책별 네트워크 + centrality \n" \
        )

main()
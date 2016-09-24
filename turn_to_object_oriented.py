#!/usr/bin/env python
#-*- coding: utf-8 -*-
import csv
import glob
import os
import shutil
import sqlite3
import grequests
import xlrd
import re
from selenium import webdriver

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import datetime
from datetime import timedelta

import pandas as pd

from Policy import Policy
import Document
from PolicyDocument import PolicyDocument
from Department import Department
from Network import Network
from Connection import Connection
from Date import Date
import numpy as np

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
        #doc_url = "http://opengov.seoul.go.kr/sanction?&startDate=%s&endDate=%s" % (policy.date.from_date, policy.date.to_date)
        doc_url = "http://opengov.seoul.go.kr/sanction?"

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
    print(receiver_text)

    if "수신" in receiver_text:
        if "수신자참조" in receiver_text:
            if "수신자" in receiver_text:
                receiver_index = receiver_text.index("수신자") + 1
                receiver = receiver_text[receiver_index]
            else:
                receiver = "No receiver"
        else:
            receiver_index = receiver_text.index("수신") + 1
            receiver = receiver_text[receiver_index]
    elif "수신자" in receiver_text:
        receiver_index = receiver_text.index("수신자") + 1
        receiver = receiver_text[receiver_index]
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
        range_idx = 10

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
        depts_divisions_list = department.get_all_departments("./data/seoul_departments_divisions.txt")
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
        depts_divisions_list = department.get_all_departments("./data/seoul_departments_divisions.txt")
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

                policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")

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
        for txt_file_name in glob.glob("/Volumes/Backup/data/txt_files/txt_files_by_policy2/*.txt"):
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
        department.write_csv_for_gephi(depts_list, filtered_connections_dict, "./data/edges_list_for_policy2.csv")

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
            policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")
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
        done_list = []

        for row in cursor:
            policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")
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

    # 33. 서울시 홈페이지 검색을 통해 정책관련문서 검색하기
    if option == '33':
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("select * from policy2")
        done_list = ['2015-101', '2015-102', '2015-103', '2015-101', '2015-102', '2015-103', '2015-104', '2015-105', '2015-106', '2015-108', '2015-109', '2015-110', '2015-111', '2015-112', '2015-113', '2015-114', '2015-115', '2015-116', '2015-117', '2015-118', '2015-119', '2015-120', '2015-121', '2015-122', '2015-123', '2015-124', '2015-125', '2015-101', '2015-102', '2015-103', '2015-104', '2015-105', '2015-106', '2015-108', '2015-109', '2015-110', '2015-111', '2015-112', '2015-113', '2015-114', '2015-115', '2015-116', '2015-117', '2015-118', '2015-119', '2015-120', '2015-121', '2015-122', '2015-123', '2015-124', '2015-125', '2015-126', '2015-127', '2015-101', '2015-102', '2015-103', '2015-104', '2015-105', '2015-106', '2015-108', '2015-109', '2015-110', '2015-111', '2015-112', '2015-113', '2015-114', '2015-115', '2015-116', '2015-117', '2015-118', '2015-119', '2015-120', '2015-121', '2015-122', '2015-123', '2015-124', '2015-125', '2015-126', '2015-127', '2015-128', '2015-129', '2015-130', '2015-131', '2015-132', '2015-136', '2015-138', '2015-139', '2015-140', '2015-141', '2015-142', '2015-143', '2015-144', '2015-145', '2015-146', '2015-147', '2015-148', '2015-149', '2015-150', '2015-151', '2015-153', '2015-154', '2015-155', '2015-156', '2015-157', '2015-158', '2015-160', '2015-162', '2015-163', '2015-164', '2015-165', '2015-166', '2015-167', '2015-168', '2015-169', '2015-170', '2015-171', '2015-172', '2015-173', '2015-174', '2015-175', '2015-176', '2015-178', '2015-179', '2015-180', '2015-181', '2015-182', '2015-183', '2015-184', '2015-185', '2015-186', '2015-187', '2015-188', '2015-189', '2015-190', '2015-191', '2015-192', '2015-193', '2015-194', '2015-195', '2015-196', '2015-197']

        for row in cursor:
            policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")
            # 정책객체 초기화
            policy.id = row["id"]
            policy.keyword = row["keyword"]
            policy.title = row["title"]

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
        depts_divisions_list = department.get_all_departments("./data/seoul_departments_divisions.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list, depts_divisions_list,
                                                                             towns_list)

        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_dept = key1[1]
            policy_title = key1[2]
            network = None
            network = Network(edges)
            print(policy_id, policy_dept)
            #network.make_whole_policy_graph(policy_id, policy_title)
            network.calculate_centrality_of_policy_graph(policy_id, policy_dept, policy_title)

    if option == '51':
        for i in range(18):
            headers = {'Content-Type': 'application/json', 'Accept-Encoding': None}
            response = requests.get(
                "http://opengov.seoul.go.kr/policy?field_policy_year_value=All&search=&items_per_page=15&page=%d&policy_year=All&policy_done=All" % i, headers=headers)

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

                policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")

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

    if option == '51-1':
        workbook1 = xlrd.open_workbook('./data/policy_list_duplicate_filtered.xlsx', 'r', encoding_override="utf-8")
        worksheet = workbook1.sheet_by_index(0)
        nrows = worksheet.nrows

        cursor = conn.cursor()

        for row_num in range(nrows):
            row_value = worksheet.row_values(row_num)

            policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")

            policy.id = row_value[0]
            policy.title = row_value[1]
            policy.department = row_value[2]
            policy.budget = row_value[3]
            policy.keyword = row_value[8]
            print(policy.keyword)

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
        depts_divisions_list = department.get_all_departments("./data/seoul_departments_divisions.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list, depts_divisions_list,
                                                                             towns_list)

        with open('policy_data2.csv', 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=",")
            print(len(filtered_edges_dict.items()))
            for key, edges in filtered_edges_dict.items():
                #print(key1[0])
                policy_id = key[0]
                policy_dept = key[1]
                policy_title = key[2]
                network = Network(edges)
                centralization_score = network.calculate_centralization_of_policy_graph(policy_id, policy_title)
                nodes_centrality_dict = network.calculate_centrality_of_policy_graph(policy_id, policy_dept, policy_title)
                nodes_closeness_centrality_dict = network.calculate_closeness_centrality_of_policy_graph(policy_id, policy_dept, policy_title)
                nodes_betweenness_centrality_dict = network.calculate_betweenness_centrality_of_policy_graph(policy_id,
                                                                                                         policy_dept,
                                                                                                         policy_title)
                cursor.execute("select * from policy")
                for row in cursor:
                    if policy_id == row["id"]:
                        print("Now: " + policy_id)
                        if policy_dept in nodes_centrality_dict.keys():
                            centrality = nodes_centrality_dict[policy_dept]
                            closeness_centrality = nodes_closeness_centrality_dict[policy_dept]
                            betweenness_centrality = nodes_betweenness_centrality_dict[policy_dept]

                        #    centrality = nodes_centrality_dict[policy_dept]
                        #print(row["id"], row["title"], policy_dept, "{0:.2f}".format(centralization_score), \
                        #                        "{0:.2f}".format(centrality), row["budget"], row["area"])

                        # 이름이 정확히 일치하는 부서가 없다면,
                        else:
                            # Just capture the department with the maximum centrality
                            policy_dept = max(nodes_centrality_dict, key=nodes_centrality_dict.get)
                            centrality = nodes_centrality_dict[policy_dept]
                            closeness_centrality = nodes_closeness_centrality_dict[policy_dept]
                            betweenness_centrality = nodes_betweenness_centrality_dict[policy_dept]
                            print(row["id"], row["title"], policy_dept, "{0:.2f}".format(centralization_score), \
                                  "{0:.2f}".format(centrality), row["period"], row["budget"], row["area"], row["num_of_google_search_results"], row["num_of_naver_search_results"])

                        print(centrality, closeness_centrality, betweenness_centrality)
                        writer.writerow([row["id"], row["title"], policy_dept, "{0:.2f}".format(centralization_score), \
                             "{0:.2f}".format(centrality), "{0:.2f}".format(closeness_centrality), "{0:.2f}".format(betweenness_centrality), \
                                         row["period"], row["budget"], row["area"], row["num_of_google_search_results"], row["num_of_naver_search_results"]])


        conn.commit()
        conn.close()

    if option == '58':
        cursor = conn.cursor()
        cursor2 = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor2.row_factory = sqlite3.Row

        policy_doc = PolicyDocument("", "", "", "", "", "", "", "", "", "", "", "", "")
        policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")
        cursor_policies = policy.get_policies(cursor)

        for policy in cursor_policies:
            cursor_policy_docs = policy_doc.get_policy_docs_by_policy_id(cursor2, policy["id"])
            date_list = []
            for row in cursor_policy_docs:
                doc_date = row["date"]
                date_list.append(datetime(int(doc_date.split('-')[0]), int(doc_date.split('-')[1]), int(doc_date.split('-')[2])))

            if date_list:
                end_date = min(date_list)
                start_date = max(date_list)

                num_of_days = start_date - end_date
            else:
                num_of_days = 0

            print(policy["id"] + ": " + str(num_of_days).replace(" days, ", "").replace(" day, ", "").replace("0:00:00", ""))





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

    ### 정책문서, degree centrality
    if option == '62':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list, towns_list)
        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_title = key1[1]
            network = None
            network = Network(edges)
            nodes_centrality_dict = network.calculate_centrality_of_policy_graph(policy_id, policy_title)

    if option == '63':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list,
                                                                             towns_list)

        policy_by_dep_matrix = []
        matrix_column_idx = dict()

        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_title = key1[1]
            network = None
            network = Network(edges)
            nodes_centrality_dict = network.calculate_centrality_of_policy_graph(policy_id, policy_title)

            for node, centrality in nodes_centrality_dict.items():
                if node not in matrix_column_idx.keys():
                    matrix_column_idx[node] = len(matrix_column_idx) - 1


        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_title = key1[1]
            network = None
            network = Network(edges)
            nodes_centrality_dict = network.calculate_centrality_of_policy_graph(policy_id, policy_title)

            policy_row = [0] * (len(matrix_column_idx) - 1)
            for node, centrality in nodes_centrality_dict.items():
                # insert the centrality into i th element of row referred by the index of matrix column index
                policy_row[matrix_column_idx[node]] = "{0:.2f}".format(centrality)

            policy_by_dep_matrix.append(policy_row)


        with open('policy_by_dep_matrix.csv', 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            for row in policy_by_dep_matrix:
                writer.writerow(row)

        csvfile.close()

    if option == '64':
        csvfile = open('policy_by_dep_matrix.csv', 'r')
        csvreader = csv.reader(csvfile)
        policy_by_dep_matrix = []
        for row in csvreader:
            policy_by_dep_matrix.append(row)

        np_matrix = np.matrix(policy_by_dep_matrix, dtype=float)
        np_transpose_matrix = np.matrix(policy_by_dep_matrix, dtype=float).transpose()

        one_mode_matrix = np_matrix * np_transpose_matrix
        print(one_mode_matrix)
        #print(size(one_mode_matrix))

        csvfile.close()

    if option == '65':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        depts_divisions_list = department.get_all_departments("./data/seoul_departments_divisions.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list, depts_divisions_list,
                                                                             towns_list)

        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_dept = key1[1]
            policy_title = key1[2]
            network = None
            network = Network(edges)
            print(policy_id, policy_dept)
            closeness_centrality_dict = network.calculate_closeness_centrality_of_policy_graph(policy_id, policy_dept, policy_title)

    if option == '67':
        department = Department("")
        depts_list = department.get_all_departments("./data/seoul_departments.txt")
        depts_divisions_list = department.get_all_departments("./data/seoul_departments_divisions.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers()
        edges_dict = connection.count_connections_by_policy(connections)

        filtered_edges_dict = department.verify_dep_names_by_policy_and_date(edges_dict, depts_list,
                                                                             depts_divisions_list,
                                                                             towns_list)

        for key1, edges in filtered_edges_dict.items():
            policy_id = key1[0]
            policy_dept = key1[1]
            policy_title = key1[2]
            network = None
            network = Network(edges)
            print(policy_id, policy_dept)
            betweenness_centrality_dict = network.calculate_closeness_centrality_of_policy_graph(policy_id, policy_dept,
                                                                                               policy_title)

    if option == '71':
        cursor1 = conn.cursor()
        cursor2 = conn.cursor()
        cursor3 = conn.cursor()

        keywords_policy1 = cursor1.execute("select id, keyword, period from policy").fetchall()
        keywords_policy2 = cursor2.execute("select id, keyword from policy2").fetchall()
        done_list = ['2015-43', '2015-49', '2015-44', '2015-51', '2015-47', '2015-42', '2015-41', '2015-48', '2015-53', '2015-55', '2015-52', '2015-50', '2015-46', '2015-54', '2015-45', '2015-36', '2015-31', '2015-37', '2015-26', '2015-30', '2015-33', '2015-38', '2015-29', '2015-34', '2015-28', '2015-27', '2015-35', '2015-40', '2015-32', '2015-39', '2015-22', '2015-20', '2015-16', '2015-14', '2015-11', '2015-15', '2015-13', '2015-12', '2015-18', '2015-21', '2015-17', '2015-23', '2015-19', '2015-24', '2015-25', '2015-9', '2014-84', '2014-82', '2015-6', '2014-80', '2015-3', '2015-4', '2014-81', '2014-83', '2015-5', '2015-8', '2015-2', '2015-10', '2015-1', '2015-7', '2014-77', '2014-75', '2014-74', '2014-73', '2014-68', '2014-66', '2014-76', '2014-64', '2014-70', '2014-65', '2014-72', '2014-79', '2014-78', '2014-71', '2014-69', '2014-53', '2014-60', '2014-54', '2014-56', '2014-62', '2014-63', '2014-49', '2014-61', '2014-59', '2014-57', '2014-52', '2014-51', '2014-58', '2014-55', '2014-50', '2014-35', '2014-34', '2014-42', '2014-47', '2014-36', '2014-46', '2014-32', '2014-41', '2014-48', '2014-37', '2014-40', '2014-38', '2014-33', '2014-39', '2014-44', '2014-23', '2014-18', '2014-30', '2014-27', '2014-17', '2014-20', '2014-24', '2014-28', '2014-25', '2014-22', '2014-26', '2014-31', '2014-19', '2014-29', '2014-21', '2014-13', '2014-10', '2014-2', '2014-4', '2014-11', '2014-3', '2014-8', '2014-15', '2014-9', '2014-16', '2014-7', '2014-6', '2014-5', '2014-14', '2014-12', '2013-29', '2013-28', '2013-31', '2013-32', '2013-33', '2013-34', '2014-1', '2013-27', '2013-35', '2013-25', '2013-30', '2013-36', '2013-39', '2013-26', '2013-37', '2013-10', '2013-22', '2013-8', '2013-13', '2013-7', '2013-9', '2013-23', '2013-17', '2013-15', '2013-24', '2013-18', '2013-14', '2013-11', '2013-19', '2013-5', '2013-1', '2013-3', '2012-50', '2013-2', '2012-35', '2012-49', '2012-48', '2012-42', '2012-41', '2012-43', '2012-47', '2012-39', '2012-38', '2012-34', '2012-36', '2012-28', '2012-12', '2012-31', '2012-30', '2012-11', '2012-15', '2012-2', '2012-33', '2012-5', '2012-6', '2012-7', '2012-10', '2012-23', '2012-13', '2012-4', '2011-114', '2011-111', '2011-97', '2011-96', '2011-107', '2011-104', '2011-112', '2011-115', '2011-105', '2011-100', '2011-103', '2011-108', '2011-119', '2011-106', '2011-122', '2011-89', '2011-86', '2011-80', '2011-77', '2011-81', '2011-94', '2011-93', '2011-85', '2011-92', '2011-87', '2011-78', '2011-79', '2011-83', '2011-82', '2011-88', '2011-59', '2011-53', '2011-71', '2011-55', '2011-51', '2011-72', '2011-57', '2011-46', '2011-62', '2011-61', '2011-45', '2011-74', '2011-60', '2011-76', '2011-58', '2011-19', '2011-42', '2011-22', '2011-43', '2011-29', '2011-39', '2011-33', '2011-44', '2011-32', '2011-27', '2011-25', '2011-21', '2011-20']

        for row in keywords_policy1:
            policy_id = row[0]
            if policy_id not in done_list:
                keywords = row[1]
                keywords = keywords.replace("\"", "")

                date = Date("", "")
                print("Previous policy period is " + row[2])
                (date.from_date, date.to_date) = date.format_date(row[2])
                date.from_date = date.set_range_of_from_date(date.from_date, "2011-01-01",
                                                             "2016-07-31")
                date.to_date = date.set_range_of_to_date(date.to_date, "2011-01-01", "2016-07-31")

                # 종료 후 한달 후까지 확장해서 검색하기
                to_date_formatted = datetime.date(int(date.to_date.split("-")[0]), int(date.to_date.split("-")[1]),
                                                  int(date.to_date.split("-")[2]))
                max_date_for_to_date = datetime.date(2016, 7, 31)

                if to_date_formatted < max_date_for_to_date:
                    date.to_date = to_date_formatted + timedelta(days=30)

                date.from_date = str(date.from_date)
                date.to_date = str(date.to_date)

                print("Updated Policy period is " + date.from_date + ", " + date.to_date)

                num_g_results = 0
                header = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106' }
                for keyword in keywords.split(","):
                    keyword_for_query = ""
                    for keyword_token in keyword.split("+"):
                        keyword_for_query += "intitle:" + keyword_token + "+"
                    response = requests.get("https://www.google.com/search",
                                            params={'q': keyword_for_query + "서울" + "+site:go.kr", 'tbs': "cdr:1,cd_min:"
                                                            + date.from_date + ".,cd_max:" + date.to_date },
                                            headers=header)
                    #response = requests.get("https://www.google.com/search", params={'q': "allintitle:" + keyword + "+site:go.kr"})response = requests.get("https://www.google.com/search", params={'q': "allintitle:" + keyword + "+site:go.kr"})
                    response_content = response.content.decode('ISO-8859-1')
                    print(response.url)
                    soup = BeautifulSoup(response.text, "lxml")
                    res = soup.find("div", {"id": "resultStats"})
                    if res == None:
                        num_g_results += 0
                    else:
                        num_g_results += int(''.join(re.findall(('([0-9]+)(?:개)'), res.text)))
                    print(keyword + ": " + str(num_g_results))

                done_list.append(policy_id)
                print(done_list)
                cursor3.execute("update policy set num_of_google_search_results=? where id=?", (num_g_results, policy_id))
                conn.commit()
        conn.close()


    if option == '72':
        cursor1 = conn.cursor()
        cursor2 = conn.cursor()
        cursor3 = conn.cursor()

        keywords_policy1 = cursor1.execute("select id, keyword, period from policy").fetchall()
        keywords_policy2 = cursor2.execute("select id, keyword, period from policy2").fetchall()

        for row in keywords_policy1:
            policy_id = row[0]
            keywords = row[1]
            keywords.replace("\"", "")
            date = Date("", "")
            print("Previous policy period is " + row[2])
            (date.from_date, date.to_date) = date.format_date(row[2])
            date.from_date = date.set_range_of_from_date(date.from_date, "2011-01-01",
                                                                       "2016-07-31")
            date.to_date = date.set_range_of_to_date(date.to_date, "2011-01-01", "2016-07-31")

            '''
            # 종료 후 한달 후까지 확장해서 검색하기
            to_date_formatted = datetime.date(int(date.to_date.split("-")[0]), int(date.to_date.split("-")[1]), int(date.to_date.split("-")[2]))
            max_date_for_to_date = datetime.date(2016, 7, 31)

            if to_date_formatted <= max_date_for_to_date:
                date.to_date = to_date_formatted + timedelta(days=30)
            '''

            date.from_date = str(date.from_date)
            date.to_date = str(date.to_date)

            from_date_form1 = date.from_date.replace("-", ".")
            to_date_form1 = date.to_date.replace("-", ".")
            from_date_form2 = date.from_date.replace("-", "")
            to_date_form2 = date.to_date.replace("-", "")
            num_n_results = 0

            print("Updated Policy period is " + date.from_date + ", " + date.to_date)

            client_id = "OdALI37PxDDUCagUkTA2"
            client_secret = "oryjGn7SCV"
            url = "https://openapi.naver.com/v1/search/news.xml?"
            header = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106 Safari/537.36' }

            for keyword in keywords.split(","):
                keyword = keyword.replace("+", "")
                url = "https://search.naver.com/search.naver?where=news&se=0&query=%s+\"서울\"" \
                                        "&ie=utf8&sm=tab_opt&sort=0&photo=0&field=0&reporter_article=&pd=3&ds=%s&de=%s" \
                                        "&docid=&nso=so:r,p:from%sto%s,a:all&mynews=0&mson=0&refresh_start=0&related=0" \
                                        % (keyword, from_date_form1, to_date_form1, from_date_form2, to_date_form2)
                response = requests.get(url, headers=header)


                response_content = response.content.decode('ISO-8859-1')
                print(response.text)
                print(url)
                soup = BeautifulSoup(response.text, "lxml")
                res = soup.find("div", {"class": "title_desc all_my"})
                if res == None:
                    num_n_results += 0
                else:
                    num_n_results += int(''.join(re.findall(('(?<=/) [0-9]+'), res.text)))
                print(keyword + ": " + str(num_n_results))

            cursor3.execute("update policy set num_of_naver_search_results=? where id=?", (num_n_results, policy_id))
            conn.commit()
        conn.close()


    ########### !!!!!!!!! 조단위 컨트롤 x
    if option == '91':
        cursor = conn.cursor()
        cursor_update = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("select * from policy")

        budget_pair_dict = { '백만': '000000', '천': '0000', '억': '00000000' }

        for row in cursor:
            budget = row["budget"]
            policy_id = row["id"]
            budget_refined_text = ""
            budget = budget.replace(",","")
            budget_numerix_suffix = ""

            if not re.findall("[0-9]", budget):
                budget_refined_text = "-"
                print(budget_refined_text)
            else:
                budget_numeric_part = ''.join(re.findall("([0-9]+)(?:[ㄱ-ㅎㅏ-ㅣ가-힣]+)", budget))
                budget_korean_suffix = ''.join(re.findall("([ㄱ-ㅎㅏ-ㅣ가-힣]+)(?:원)", budget))

                for budget_korean, budget_numeric in budget_pair_dict.items():
                    if budget_korean == budget_korean_suffix:
                        budget_numerix_suffix = budget_numeric

                budget_refined_text = budget_numeric_part + budget_numerix_suffix
                print(budget_refined_text)

            cursor_update.execute("update policy set budget=? where id=?", (budget_refined_text, policy_id))

        conn.commit()
        conn.close()

    if option == '92':
        cursor = conn.cursor()
        cursor_update = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("select * from policy")

        for row in cursor:
            policy_id = row["id"]
            policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")
            policy.date = Date("", "")
            print("Policy period is " + row["period"])
            (policy.date.from_date, policy.date.to_date) = policy.date.format_date(row["period"])

            policy.date.from_date = policy.date.set_range_of_from_date(policy.date.from_date, "2011-01-01",
                                                         "2016-07-31")
            policy.date.to_date = policy.date.set_range_of_to_date(policy.date.to_date, "2011-01-01", "2016-07-31")

            period_refined_text = policy.date.from_date + " ~ " + policy.date.to_date
            print(period_refined_text)
            cursor_update.execute('update policy set period=? where id=?', (period_refined_text, policy_id))

        conn.commit()
        conn.close()

    if option == '93':
        cursor = conn.cursor()
        cursor_update = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("select * from policy")

        for row in cursor:
            policy_id = row["id"]
            policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")
            policy.date = Date("", "")
            period = row["period"]
            print("Policy period is " + row["period"])
            from_date_str = period.split(" - ")[0]
            to_date_str = period.split(" - ")[1]
            from_date = from_date_str[:4] + "-" + from_date_str[4:6] + "-" + from_date_str[5:7]
            to_date = to_date_str[:4] + "-" + to_date_str[4:6] + "-" + to_date_str[5:7]
            period_refined = from_date + " ~ " + to_date
            print(period_refined)

            #cursor_update.execute('update policy set period=? where id=?', (period_refined, policy_id))

        #conn.commit()
        #conn.close()

    if option == '94':
        for i in range(18):
            headers = {'Content-Type': 'application/json', 'Accept-Encoding': None,
                       'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106 Safari/537.36' }
            response = requests.get(
                "http://opengov.seoul.go.kr/policy?field_policy_year_value=All&search=&items_per_page=15&page=%d&policy_year=All&policy_done=All" % i, headers=headers)

            cursor = conn.cursor()

            # 이미 저장된 정책들은 다시 방문하지 않는다

            policy_urls = re.findall('\/policy\/project\/[0-9]+', response.content.decode())  # 정책 url
            policy_urls = set(policy_urls)
            # 정책 리스트 한 페이지 내에 있는 정책 loop
            for policy_url in policy_urls:
                url = "http://opengov.seoul.go.kr" + policy_url
                print(url)
                response2 = requests.get(url, headers=headers)  # Project information page
                response2_content = response2.content.decode().replace('\n', '').replace('\t', '')
                print(response2.content)

                policy = Policy("", "", "", "", "", "", "", "", "", "", "", "")

                print("Starting this policy url: " + "http://opengov.seoul.go.kr" + policy_url)
                policy.id = re.findall('(?:사업번호</th><td>)([0-9-]+)(?:<)', response2_content)[0]
                policy.period = re.findall('(?:기간</th><td>)(.*?)(?:<)', response2_content)[0]

                print(policy.id, policy.period)

                cursor.execute("update policy set period=? where id=?", (policy.period, policy.id))

                conn.commit()
        conn.close()

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
        "\t 41. 정책문서 시각화(정책별/월별) \n" \
        "\t 42. 정책문서 시각화(정책별) \n" \

        "그룹 5. DB queries \n" \
        "\t 51. Insert: 정책 데이터 저장 \n" \
        "\t 51-1. Insert: 정책 데이터 from 평가자료 저장 \n" \
        "\t 52. Insert: 월별 수신자 정보 추출 from txt files & 저장\n"\
        "\t 53. Update: 정책 키워드 입력하기"
        "\t 56. Select: 일반문서 데이터를 정책 키워드로 검색하여 정책관련문서 추리기 \n" \
        "\t 57. !!!!!Select: 정책별 사업번호, 사업명, 주무부서 and centralization, centrality of primary department -> csv로 출력 \n" \
        "\t 58. Select: policy 별로 policy documents들의 가장 빠른 문서와 가장 나중 문서의 차를 구해서 기간이 얼마나 되는지 도출해내기 \n" \
 \
        "그룹 6. 네트워크 속성 \n" \
        "\t 61. 정책별 네트워크 + centralization  \n" \
        "\t 62. 정책별 네트워크 + degree centrality \n" \
        "\t 63. policy by department matrix for centrality and export to csv \n" \
        "\t 64. import two mode matrix, multiply by transposed one, then get one-mode \n" \
        "\t 65. 정책별 네트워크 + closeness centrality \n" \

        "그룹 7. 검색 엔진 크롤링 \n" \
        "\t 71. 정책 키워드로 구글에서 go.kr 검색결과 개수 도출  \n" \
        "\t 72. 정책 키워드로 네이버에서 뉴스 검색결과 개수 도출  \n" \

        "그룹 9. etc \n" \
        "\t 91. 예산 데이터를 numeric으로 정제  \n" \
        "\t 92. 기간 데이터를 numeric으로 정제(YYYY-MM-DD ~ YYYY-MM-DD)  \n" \
        "\t 94. 정책기간 데이터 크롤링 후 DB에 업데이트  \n" \
        )

main()
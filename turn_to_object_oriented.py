#!/usr/bin/env python
#-*- coding: utf-8 -*-
import csv
import glob
import os
import sqlite3
import grequests
import re

import requests
from tqdm import tqdm
from datetime import datetime, timedelta
import pandas as pd

from Policy import Policy
from Document import Document
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
    responses = (grequests.get(doc.url) for doc in doc_list)

    # Cursor for DB
    cursor1 = conn.cursor()

    #print "# of requests: " + str(len(grequests.map(responses)))
    for response in grequests.map(responses):
        if response != None:
            file_name = re.findall('fid=(.*?)"', response.content.decode("utf-8"))
            # 엑셀문서에 나와있는 날짜가 틀린 경우가 있다. 이런 경우 날짜를 직접 문서상에서 찾아줘야 한다.....
            date_in_doc = re.findall(r'2F[0-9]{8}', response.content.decode("utf-8"))
            url_for_html_file = 'http://opengov.seoul.go.kr/synap/output' + '/' + ''.join(file_name) + '.view.xhtml'
            hwp_file_name = ''.join(file_name) + ".hwp"
            #print("hwp_file_name here: " + hwp_file_name)
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
        print(doc)
        # url_for_hwp_file이 비어있는 경우를 피한다
        print("url for hwp file is " + doc.url_for_hwp_file)
        if doc.url_for_hwp_file:
            headers = {'Connection': 'close'}
            # Request timeout가 아닐 경우에만 진행
            try:
                response2 = requests.get(doc.url_for_hwp_file, headers=headers, timeout=15)   # doc_info[9] = url_for_hwp_file
                print("response2 done")
                with open(doc.hwp_file_name, "wb") as handle: # doc_info[10] = hwp_file_name
                    print("start downloading")
                    for data in tqdm(response2.iter_content()):
                        handle.write(data)

                ### Change the name of hwp folders
                ### hwp 파일명을 기존 파일명에서 [날짜]_[id] 로 바꾼다

                previous_hwp_file_name = doc.hwp_file_name
                new_hwp_file_name = str(doc.idx) + "_" + str(doc.date) + "_" + str(doc.doc_id) + ".hwp"
                # 새 이름을 doc_info[10]에 저장
                doc.hwp_file_name = new_hwp_file_name
                # 새 경로를 지정
                hwp_file_new_path = "./data/hwp_files/hwp_files_%s/" % current_month + new_hwp_file_name
                # 기존 이름(previous_hwp_file_name) => 새 이름(new_hwp_file_name)
                print("New hwp file path is " + hwp_file_new_path)
                print("Previous hwp file name is " + previous_hwp_file_name)
                # hwp 파일이름을 바꾼다
                # hwp파일이 전송된 것이 있을 경우에만 파일이름을 바꾼다
                if previous_hwp_file_name:
                    os.rename(previous_hwp_file_name, hwp_file_new_path)
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
        print(keyword)
        doc_url = "http://opengov.seoul.go.kr/sanction?&startDate=%s&endDate=%s" % (policy.date.from_date, policy.date.to_date)
        for keyword_token in keyword.split("+"):
            url_for_keyword = "&searchField%" + "5B%" + "5D=TITLE&searchFieldOpt%" + "5B%" + "5D=%" + "3A&searchFieldKeyword%" + "5B%" + "5D=%s" % keyword_token
            doc_url += url_for_keyword
        response = requests.get(doc_url)
        print(doc_url)
        response_content = response.content.decode()

        # 문서리스트 페이지 돌기
        # 페이지 개수는 (문서 총개수(마지막문서의 인덱스) / 10)의 몫
        last_page_idx = re.findall('(?:"hide-mobile">)([0-9]{,3})(?:</td>)', response_content)
        # 정책과 관련된 문서가 없어서 인덱스가 없는 경우가 있으므로 체크..
        if last_page_idx:
            print("biggest index is " + last_page_idx[0])
            last_page_idx = (int(last_page_idx[0]) // 15) + 1

            for i in range(last_page_idx):
                #http://opengov.seoul.go.kr/sanction?page=1&startDate=2011-01-01&endDate=2016-04-30&searchField%5B%5D=TITLE&searchFieldOpt%5B%5D=%3A&searchFieldKeyword%5B%5D=한양도성&searchField%5B%5D=TITLE&searchFieldOpt%5B%5D=%3A&searchFieldKeyword%5B%5D=유네스코
                response2 = requests.get("http://opengov.seoul.go.kr/sanction" + "?page=" + str(i) + doc_url.replace("http://opengov.seoul.go.kr/sanction",""))
                print("http://opengov.seoul.go.kr/sanction" + "?page=" + str(i) + doc_url.replace("http://opengov.seoul.go.kr/sanction",""))
                response_content2 = response2.content.decode().replace('\n', '').replace('\t', '')
                print("Page " + str(i+1) + " of " + policy.id)

                doc_ids = re.findall('(?:\"hide-mobile">)([0-9]{,3})(?:</td>)', response_content2)
                titles = [ title.replace("<em class=\"search-highlight\">","").replace("</em>","") for title in re.findall('(?:"tbl-tit">)(.*?)(?:</strong>)', response_content2) ]
                document_urls = re.findall("(\/sanction\/[0-9]+)(?:\"><strong)", response.content.decode())
                document_urls = list(set(document_urls))
                dates = re.findall("[0-9]{4}-[0-9]{2}-[0-9]{2}", response_content2)
                is_publics = re.findall("(?:\"txt-icon tbl-cat\">)([0-9ㄱ-ㅎㅏ-ㅣ가-힣(), ]+)(?:</span>)", response_content2)

                doc_list = []
                # Assign to each PolicyDocument
                for doc_id, title, url, date, is_public in zip(doc_ids, titles, document_urls, dates, is_publics):
                    print('{} {} {}'.format(doc_id, title, url, date, is_public))
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
                    print(doc.doc_id, doc.policy_id, doc.url)

                print(doc_list)

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
                        #if not date_in_doc:
                        #    date_in_doc.append(str(datetime.strptime(doc.date, "%Y-%m-%d") - timedelta(days=1)).replace('00:00:00', '').replace('-', '').replace(' ', ''))

                        url_for_hwp_file = re.findall("\/sites\/all\/blocks\/download.php\?uri=%2Fdcdata%2F100001%2F[0-9]+%2FF[0-9]+.hwp", response_content)
                        if url_for_hwp_file:
                            url_for_hwp_file = "http://opengov.seoul.go.kr" + url_for_hwp_file[0]
                        else:
                            url_for_hwp_file = ""
                        url_name = re.findall('(http:\/\/opengov.seoul.go.kr\/sanction\/[0-9]+)', response_content)[0]

                        # Get information from the table in the webpage
                        for doc in doc_list:
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
                            new_hwp_file_name = str(doc.policy_id) + "_s" + str(doc.doc_id) + "_" + str(doc.date.replace('-','')) + ".hwp"
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
    receiver_text_string = ''.join(receiver_text)

    if '수신' in receiver_text_string: # or (receiver_text_string.find(u'수신') != -1):   # !!!!!!!!! 수 신 자 도 잡아내자
        receiver_text_string = receiver_text_string[(receiver_text_string.index('수신')+len('수신')):]
        # 수신자 단어 외에 '수신자 참조'라는 단어가 있어서 '수신자'가 제대로 잡히지 않은 경우, 다시 한번 잡아낸다
        if '수신자' in receiver_text_string:
            receiver_text_string = receiver_text_string[(receiver_text_string.index('수신자')+len('수신자')):]
        # '수신자참조'가 있는 경우, 문서 하단에 수신자가 나열되어 있는 경우가 있다. 그러므로 '수신자' 단어를 다시 한번 잡아내야 한다
        if '수신자' in receiver_text_string:
            receiver_text_string = receiver_text_string[(receiver_text_string.index('수신자')+len('수신자')):]
        # 두번째 등장하는 </span>까지 자르면 수신자 목록만 남게 된다
        try:
            span_index = receiver_text_string.index('</CHAR>')
            span_index2 = receiver_text_string.index('</CHAR>', receiver_text_string.index('</CHAR>')+1)
            # 마침내 수신자 목록을 얻었다..하....
            receiver = receiver_text_string[span_index + len('</CHAR>'):span_index2]
            # 공백이 있는 경우 제거하기
            receiver = receiver.replace(" ", "")
            # match = hangul.search(receiver_text_string)
            # print receiver_text_string[match.start():match.end()]
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

    policy_id = re.findall(r'([0-9]+-[0-9]+)(?:_)', txt_file_name)[0]
    doc_id = re.findall(r'(?:_)([0-9]+)(?:_)', txt_file_name)[0]

    receiver_text = re.findall(r'[0-9ㄱ-ㅎㅏ-ㅣ가-힣(), ]+</CHAR>', hwp_code)
    receiver_text_string = ''.join(receiver_text)

    if '수신' in receiver_text_string: # or (receiver_text_string.find(u'수신') != -1):   # !!!!!!!!! 수 신 자 도 잡아내자
        receiver_text_string = receiver_text_string[(receiver_text_string.index(u'수신')+len(u'수신')):]
        # 수신자 단어 외에 '수신자 참조'라는 단어가 있어서 '수신자'가 제대로 잡히지 않은 경우, 다시 한번 잡아낸다
        if '수신자' in receiver_text_string:
            receiver_text_string = receiver_text_string[(receiver_text_string.index(u'수신자')+len(u'수신자')):]
        # '수신자참조'가 있는 경우, 문서 하단에 수신자가 나열되어 있는 경우가 있다. 그러므로 '수신자' 단어를 다시 한번 잡아내야 한다
        if '수신자' in receiver_text_string:
            receiver_text_string = receiver_text_string[(receiver_text_string.index(u'수신자')+len(u'수신자')):]
        # 두번째 등장하는 </span>까지 자르면 수신자 목록만 남게 된다
        span_index = receiver_text_string.index('</CHAR>')
        span_index2 = receiver_text_string.index('</CHAR>', receiver_text_string.index('</CHAR>')+1)
        # 마침내 수신자 목록을 얻었다..하....
        receiver = receiver_text_string[span_index+len('</CHAR>'):span_index2]
        # 공백이 있는 경우 제거하기
        receiver = receiver.replace(" ", "")
        #match = hangul.search(receiver_text_string)
        #print receiver_text_string[match.start():match.end()]
        print("receiver: " + receiver)

        # regex에서 도출된 row index 텍스트에서 _를 제외한다
        return (policy_id, doc_id, receiver)
    else:
        receiver = "No receiver"
        print("No receiver")
        return (policy_id, doc_id, receiver)


def main():
    option = input("Select menu: ")
    conn = sqlite3.connect("./seoul_documents.db")
    connection = Connection("", "", "", "")

    if option == "1":
        current_month = input("Enter a month (e.g., 201501) : ")
        start_idx = int(input("Enter the start index : "))

        end_idx = 0
        range_idx = 50

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
                    doc = Document("", "", "", "", "", "", "", "", "", "", "", "")
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
        # argument: idx, work_category, title, sender, receiver
        document = Document("", "", "", "", "")
        documents = document.get_doc_info(1, 1)
        document.write_results_to_txt("doc_info_201501.txt", documents)

    if option == '8':
        department = Department("")
        depts_list = department.get_all_departments("seoul_departments.txt")
        towns_list = department.get_all_towns_in_seoul()
        connections = connection.get_senders_and_receivers_by_month(1, 1)
        counted_connections = connection.count_connections(connections)
        filtered_connections_dict = department.verify_dep_names_from_txt_file("edges_201501.txt", depts_list,
                                                                              towns_list)
        department.write_csv_for_gephi(depts_list, filtered_connections_dict, "edges_list_201501.csv")

    if option == '9':
        document = Document()
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
        for txt_file_name in glob.glob("./txt_files_by_policy/*.txt"):
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
        doc = Document("", "", "", "", "", "", "", "", "", "", "", "")
        policy_doc = PolicyDocument("", "", "", "", "", "", "", "", "", "", "", "", "")

        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("select * from policy")
        policies = []

        for row in cursor:
            policy = Policy("", "", "", "", "", "", "", "", "", "")
            # 정책객체 초기화
            policy.id = row["id"]
            policy.date = Date("", "")
            policies.append(policy)
            ### 각 정책별로 처리..

        # for policy in policies:
        # Go over documents from the policy period
        # 정책마다 날짜 포맷이 다르므로 각기 다르게 대응

        # 여러 세트의 키워드를 넘긴다

        #policies[0].keywords = keywords

        doc.get_doc_info_by_policy_keywords(policies[0].id, policies[0].period, policies[0].keywords)


        # policy_doc.insert_relevant_doc_info_by_policy()

    if option == '32':
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("select * from policy")

        for row in cursor:
            policy = Policy("", "", "", "", "", "", "", "", "", "")
            # 정책객체 초기화
            policy.id = row["id"]
            policy.keyword = row["keyword"]
            policy.date = Date("", "")
            (policy.date.from_date, policy.date.to_date) = policy.date.format_date(row["period"])
            print(policy.date.from_date, policy.date.to_date)

            Find_hwp_file_name_and_download_hwp_by_search_for_policy(policy, conn)

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
            network = None
            network = Network(edges)
            network.make_graph(policy_id, month)

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
    if option == '53':
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


    if option == '99':
        doc_url = "http://opengov.seoul.go.kr/sanction/9176301"
        str_1 = "http://opengov.seoul.go.kr" + doc_url.replace("http://opengov.seoul.go.kr", "")
        print(str_1)

def menu():

    print(
        "그룹 1. 일반문서 크롤링 \n" \
        "\t 1. 일반문서 크롤링 : 원하는 기간 선택, DB에 정보 저장, 한글파일 다운로드 \n" \
        "\t 2. txt 파일로 변환 \n" \
        "\t 4. DB로부터 송수신자 받아서 출력하기\n" \
        "\t 5. 송수신자 종류별로 주고받은 문서개수 세고 딕셔너리에 저장하기\n" \
        "\t 6. 송수신자 정보 csv에 출력하기\n" \
        "\t 7. 문서 정보 txt에 출력하기\n" \
        "\t 8. 서울시 내부부서만 가려내서 출력하기\n"
        "\t 9. 조건에 맞는 문서개수 파악하기\n"

        "그룹 2. 정책관련문서 크롤링 \n" \
        "\t 11. 정책관련문서 크롤링 : \n" \
        "\t 12. 정책관련문서 수신자정보 추출 \n" \
        "\t 14. DB로부터 송수신자 받고 -> 외부기관 제외 & 송수신자 일대일로 처리\n" \
        "\t 15. 송수신자 종류별로 주고받은 문서개수 세고 딕셔너리에 저장하기\n" \

        "그룹 3. 일반문서로부터 정책 키워드로 크롤링 \n"\
        "\t 31. 일반문서로부터 정책키워드로 정책과 관련된 일반문서 가져오기 \n" \
        "\t 32. 서울시 홈페이지 검색을 통해 정책관련문서 검색하기 \n"\

        "그룹 3. 네트워크 시각화 \n" \
        "\t 41. 정책문서 시각화 \n" \

        "그룹 4. DB queries \n" \
        "\t 51. Insert: 정책 데이터 저장 \n" \
        "\t 52. Insert: 월별 수신자 정보 추출 from txt files & 저장\n"\
        "\t 53. Update: 정책 키워드 입력하기"
        "\t 56. Select: 일반문서 데이터를 정책 키워드로 검색하여 정책관련문서 추리기 \n" \
        )

main()
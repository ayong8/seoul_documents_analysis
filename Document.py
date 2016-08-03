import sqlite3
import csv
import re
import os
from datetime import datetime
import pandas as pd


DATABASE_NAME = './seoul_documents.db'

class Document:
    def __init__(self, doc_id, idx, date, title, writer, work_category, sender, receiver, url, url_for_html_file, url_for_hwp_file, hwp_file_name):
        self.doc_id = doc_id
        self.idx = idx
        self.date = date
        self.writer = writer
        self.work_category = work_category
        self.title = title
        self.sender = sender
        self.receiver = receiver
        self.url = url
        self.url_for_html_file = url_for_html_file
        self.url_for_hwp_file = url_for_hwp_file
        self.hwp_file_name = hwp_file_name

    def filter_and_insert_doc_info_to_DB(self, doc_info):
        useless_work_cards = [u'예산집행및회계관리', u'복무관리', u'공무직관리', u'관용차량관리', u'인사관리', u'급여및수당관리', u'교육훈련관리']
        useless_title_words = [u'일지', u'휴가']

        # row_value[0]: package_id, 1: date, 2: work category, 3: title, 4: doc num
        # 5: writer, 6: preservation period, 7: 발신부서, 8: public or not, 9: copyright, 10: url
        ### 공개 = 1, 비공개 = 0, 부분공개 = 2
        # 문서가 비공개가 아닐 경우, 그리고 문서 url이 존재하는 문서들만 작업을 진행 (공개 혹은 부분공개일 경우...)
        if (doc_info[8] != 0) and (doc_info[9] != None):
            # 업무교류와 관계없는 과제카드들을 제외
            if doc_info[5] not in useless_work_cards:
                # 업무교류와 상관없는 제목을 가진 문서들을 제외
                if all(word not in doc_info[6] for word in useless_title_words):
                    self.idx = doc_info[0]
                    self.doc_id = str(doc_info[1])
                    self.date = doc_info[4]
                    self.title = doc_info[6]
                    self.writer = doc_info[7]
                    self.receiver = doc_info[2]
                    self.url = doc_info[9]
                    self.url_for_html_file = ''
                    self.url_for_hwp_file = ''
                    self.hwp_file_name = ''

    def extract_doc_info_from_web_for_policy(self):
        pass

    def count_documents_by_condition(self):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        result = cursor.execute("select count(*) from documents_201501 where (public = 1 or public = 2)")
        for i in result:
            print(i)

    def get_doc_info(self, from_month, to_month):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        documents = []

        # Put together connections of all months
        for i in range(from_month, to_month + 1):
            # 2d array expected (e.g., [ [sender1, receiver1-1,receiver1-2], [sender2, receiver2], ... ]
            if i < 10:
                documents_for_month = cursor.execute("SELECT idx, work_category, title, sender, receiver FROM documents_20150%d" % i)
            else:
                documents_for_month = cursor.execute("SELECT idx, work_category, title, sender, receiver FROM documents_2015%d" % i)

            for doc in documents_for_month:
                document = Document(doc[0], doc[1], doc[2], doc[3], doc[4])
                documents.append(document)

        conn.commit()
        conn.close()

        return documents

    def get_doc_info_by_policy_keywords(self, policy, conn):
        import PolicyDocument

        cursor = conn.cursor()
        cursor2 = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor2.row_factory = sqlite3.Row

        from_date = datetime(int(policy.date.from_date.split('-')[0]), int(policy.date.from_date.split('-')[1]), int(policy.date.from_date.split('-')[2]))
        to_date = datetime(int(policy.date.to_date.split('-')[0]), int(policy.date.to_date.split('-')[1]), int(policy.date.to_date.split('-')[2]))

        date_dict = pd.DataFrame(pd.date_range(from_date, to_date, freq='M'))

        for keyword in policy.keyword.split(","):
            query_for_keywords = ""
            tokens = []
            print("whole keyword: " + keyword)
            for idx, keyword_token in enumerate(keyword.split("+")):
                if idx == 0:
                    query_for_keywords += "title LIKE ?"
                else:
                    query_for_keywords += "and title LIKE ?"
                tokens.append(keyword_token.replace("\n", ""))
            # 키워드가 없다면 해당 키워드에 대해 아래 코드를 실행하지 않는다
            if not tokens:
                continue
            print("split keyword by +: " + ''.join(tokens))
            for idx, date in date_dict.items():
                months = [month.replace('-', '') for month in re.findall('[0-9]{4}-[0-9]{2}', str(date))]
                for current_month in months:
                    query = "select * from documents_" + current_month + " where " + query_for_keywords + "COLLATE NOCASE" # Case-insensitive
                    params = tuple(tokens)
                    print("current month: " + current_month)
                    if len(tokens) == 1:
                        results = cursor.execute(query, ['%'+tokens[0]+'%'])
                    if len(tokens) == 2:
                        results = cursor.execute(query, ['%'+tokens[0]+'%','%'+tokens[1]+'%'])
                    if len(tokens) == 3:
                        results = cursor.execute(query, ['%'+tokens[0]+'%', '%'+tokens[1]+'%', '%'+tokens[2]+'%'])
                    #existing_policy_docs = policy_doc.get_policy_urls_by_policy_id()
                    for result in results:
                        policy_doc = PolicyDocument.PolicyDocument("","","","","","","","","","","","","")
                        policy_doc.policy_id = policy.id
                        policy_doc.policy_title = policy.title
                        policy_doc.doc_id = result["doc_id"]
                        policy_doc.title = result["title"]
                        policy_doc.date = result["date"]
                        policy_doc.sender = result["sender"]
                        policy_doc.receiver = ""
                        policy_doc.writer = result["writer"]
                        policy_doc.url = result["url"]
                        policy_doc.url_for_html_file = result["url_for_html_file"]
                        policy_doc.url_for_hwp_file = result["url_for_hwp_file"]
                        policy_doc.hwp_file_name = result["hwp_file_name"]
                        policy_doc.is_public = result["public"]

                        # DB에 넣고, 한글파일을 일반문서폴더에서 hwp_files_by_policy로 끌어오기
                        #if policy_doc.url in existing_policy_docs:
                        previous_file_name = str(result["idx"]) + "_" + str(result["date"]) + "_" + str(result["doc_id"]) + ".hwp"
                        previous_file_path = "/Volumes/Backup/data/hwp_files/hwp_files_%s/%s" % (current_month, previous_file_name)
                        # 해당파일이 현재 폴더에 없다면 부적합(내부결재 혹은 비공개)한 파일인 것
                        if os.path.exists(previous_file_path):
                            print(previous_file_name)
                            new_file_name = policy_doc.policy_id + "_" + str(policy_doc.doc_id) + "_" + policy_doc.date + ".hwp"
                            os.rename(previous_file_path, "/Volumes/Backup/data/hwp_files/hwp_files_by_policy/%s" % new_file_name)
                            policy_doc.insert_relevant_doc_info_by_policy(cursor2)

                    conn.commit()

    def write_results_to_txt(self, txt_file_name, documents):
        with open(txt_file_name, 'w') as txtfile:
            for document in documents:
                if not document.receiver:
                    document.receiver = ""
                    print(str(document.idx) + "\t" + document.work_category + "\t" + document.title + "\t" + document.sender + "\t" + document. receiver)
                    txtfile.write(str(document.idx) + "\t" + document.work_category + "\t" + document.title + "\t" + document.sender + "\t" + document. receiver)

    def verify_dep_names_from_txt_file(self, txt_file_name, depts_list, towns_list):
        # If there is a match
        txt_file = open(txt_file_name, "r")
        filtered_output = {}
        total_count = 0

        for line in txt_file.readlines():
            # print line
            sender = line.split(" ")[0]
            receiver = line.split(" ")[1]
            count = line.split(" ")[2]
            # print(sender, receiver, count)

            if any(dept in receiver for dept in depts_list):
                for dept1 in depts_list:
                    if dept1 in receiver:
                        if '(' in receiver:
                            if all(town not in receiver for town in towns_list) and ('서울특별시' in receiver):
                                print(sender, dept1, count)
                                filtered_output[(sender, dept1)] = count
                                total_count += int(count)
                        else:
                            print(sender, dept1, count)
                            filtered_output[(sender, dept1)] = count
                            total_count += int(count)

        print("total count of filtered docs: " + str(total_count))
        return filtered_output
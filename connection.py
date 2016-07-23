#!/usr/bin/env python
#-*- coding: utf-8 -*-

import sqlite3
import csv
#import unicodecsv
import sys
import codecs

DATABASE_NAME = "seoul_documents.db"

class Document:
    def __init__(self, idx, work_category, title, sender, receiver):
        self.idx = idx
        self.work_category = work_category
        self.title = title
        self.sender = sender
        self.receiver = receiver

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

class Connection:
    def __init__(self, doc_idx, sender, receiver):
        self.doc_idx = doc_idx
        self.sender = sender
        self.receiver = receiver
        self.connections = {}

    # connections = set of Connection instances
    ### Count edges by senders and receivers and put them in the dictionary
    def count_connections(self, connections):
        connection_counter_dict = {}
        for connection in connections:
            sender = connection.sender
            receivers = connection.receiver
            # If sender and receiver exist
            if sender and receivers and (receivers != 'No receiver'):
                # Iterate over all receivers if there are more than two receivers
                for receiver in receivers.split(","):
                    # There is same entry that was already inserted in the dictionary,
                    if (sender, receiver) in connection_counter_dict.keys():
                        connection_counter_dict[(sender, receiver)] += 1
                    else:
                        connection_counter_dict[(sender, receiver)] = 1

        with open("edges_201501.txt", "w") as txt_file:
            for key, count in connection_counter_dict.items():
                print(key[0], key[1], count)
                txt_file.write(key[0] + " " + key[1] + " " + str(count) + "\n")


    ### Get all senders and receivers from desirable period of months
    # input should be two digits of a month (e.g., 01, 03, 10)
    def get_senders_and_receivers(self, from_month, to_month):
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        connections = []

        # Put together connections of all months
        for i in range(from_month, to_month+1):
            # 2d array expected (e.g., [ [sender1, receiver1-1,receiver1-2], [sender2, receiver2], ... ]
            if i < 10:
                connections_for_month = cursor.execute("SELECT idx, sender, receiver FROM documents_20150%d" % i)
            else:
                connections_for_month = cursor.execute("SELECT idx, sender, receiver FROM documents_2015%d" % i)
            for connection in connections_for_month:
                connection = Connection(connection[0], connection[1], connection[2])
                connections.append(connection)

        conn.commit()
        conn.close()

        return connections

    def write_connections_to_csv(self, csv_file_name, connections):
        with open(csv_file_name, 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            for connection in connections:
                writer.writerow([connection.doc_idx, connection.sender, connection.receiver])

class Department:
    def __init__(self, name):
        self.name = name

    def get_all_departments(self, txt_file_name):
        txt_file = open(txt_file_name, "r")
        depts_list = []
        for line in txt_file.readlines():
            depts_list.append(line.replace("\n",""))
            #print(line)

        #print(depts_list)
        return depts_list

    # List of region names that should be deleted
    def get_all_towns_in_seoul(self):
        return ['종로', '용산', '광진', '중랑', '강북', '노원', '서대문', '양천', '구로', '영등포', '관악', '강남', '강동', \
                '중구', '성동', '동대문', '성북', '도봉', '은평', '마포', '강서', '금천', '동작', '서초', '송파']

    def verify_dep_names(self, connections, depts_list, towns_list):
        # If there is a match
        for connection in connections:
            if (connection.sender in depts_list) and (connection.receiver in depts_list):
                if '(' in connection.receiver:
                    for town in towns_list:
                        if town not in connection.receiver:
                            print(connection.sender, connection.receiver)


    def verify_dep_names_from_txt_file(self, txt_file_name, depts_list, towns_list):
        print("here")
        # If there is a match
        txt_file = open(txt_file_name, "r")
        filtered_output = {}
        total_count = 0

        for line in txt_file.readlines():
            #print line
            sender = line.split(" ")[0]
            receiver = line.split(" ")[1]
            count = line.split(" ")[2]
            #print(sender, receiver, count)

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

    def write_csv_for_gephi(self, depts_list, filtered_connections_dict, csv_file_name):
        with open(csv_file_name, 'w') as csvfile:
            writer = csv.writer(csvfile, delimiter=',')
            # Write sender to the first line
            writer.writerow(["Source", "Target", "Weight"])
            for key, value in filtered_connections_dict.items():
                sender = key[0]
                receiver = key[1]
                weight = value
                writer.writerow([sender, receiver, weight])



def main():

    option = input(print_menu())
    # Pull up connections
    connection = Connection("", "", "")

    while option != '9':

        if option == '1':
            connections = connection.get_senders_and_receivers(1, 1)

        if option == '2':
            connections = connection.get_senders_and_receivers(1, 1)
            connection.count_connections(connections)
            #for connection in connections:
            #    print(connection.sender, connection.receiver)

        if option == '3':
            #Write csv file
            connection.write_connections_to_csv("connections.csv", connections)

        if option == '4':
            # argument: idx, work_category, title, sender, receiver
            document = Document("", "", "", "", "")
            documents = document.get_doc_info(1, 1)
            document.write_results_to_txt("doc_info_201501.txt", documents)

        if option == '5':
            department = Department("")
            depts_list = department.get_all_departments("seoul_departments.txt")
            towns_list = department.get_all_towns_in_seoul()
            connections = connection.get_senders_and_receivers(1, 1)
            counted_connections = connection.count_connections(connections)
            filtered_connections_dict = department.verify_dep_names_from_txt_file("edges_201501.txt", depts_list, towns_list)
            department.write_csv_for_gephi(depts_list, filtered_connections_dict, "edges_list_201501.csv")

        if option == '6':
            document = Document()
            document.count_documents_by_condition()

        option = input(print_menu())


def print_menu():
    print("Please choose an option: \n" \
            "1. DB로부터 송수신자 받아서 출력하기\n" \
            "2. 송수신자 종류별로 주고받은 문서개수 세고 딕셔너리에 저장하기\n" \
            "3. 송수신자 정보 csv에 출력하기\n" \
            "4. 문서 정보 txt에 출력하기\n" \
            "5. 서울시 내부부서만 가려내서 출력하기\n"
            "6. 조건에 맞는 문서개수 파악하기\n")

main()
import sqlite3
import csv

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

    ### txt 파일로
    def verify_dep_names_from_txt_file(self, txt_file_name, depts_list, towns_list):
        print("here")
        # If there is a match
        txt_file = open(txt_file_name, "r")
        filtered_output = {}
        total_count = 0

        for line in txt_file.readlines():
            #print line
            sender = line.split("\t")[0]
            receiver = line.split("\t")[1]
            count = line.split("\t")[2]
            #print(sender, receiver, count)
            #print(receiver)

            if any(dept in receiver for dept in depts_list):
                for dept1 in depts_list:
                    if dept1 in receiver:
                        if '(' in receiver:
                            if all(town not in receiver for town in towns_list) and ('서울특별시' in receiver):
                                #print(sender, dept1, count)
                                filtered_output[(sender, dept1)] = count
                                total_count += int(count)
                        else:
                            #print(sender, dept1, count)
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
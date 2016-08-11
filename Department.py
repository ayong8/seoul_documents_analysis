import sqlite3
import csv
import copy

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

    ### Input: counted_connections_dict => (sender, receiver) : count
    def verify_dep_names(self, counted_connections_dict, depts_list, towns_list):
        total_count = 0
        filtered_output = {}

        for key, count in counted_connections_dict.items():
            sender = key[0]
            receiver = key[1]

            if any(dept in receiver for dept in depts_list):
                for dept1 in depts_list:
                    if dept1 in receiver:
                        if '(' in receiver:
                            if all(town not in receiver for town in towns_list) and ('서울특별시' in receiver):
                                filtered_output[(sender, dept1)] = count
                                total_count += int(count)
                        else:
                            #print(sender, dept1, count)
                            filtered_output[(sender, dept1)] = count
                            total_count += int(count)

        print("total count of filtered docs: " + str(total_count))
        return filtered_output

    def verify_dep_names_by_policy_and_date(self, edges_dict, depts_list, towns_list):
        total_count = 0
        filtered_edges_dict = {}

        for key, edges in edges_dict.items():
            for edge, count in edges.items():
                sender = edge[0]
                receiver = edge[1]
                if any(dept in receiver for dept in depts_list):
                    for dept1 in depts_list:
                        if dept1 in receiver:
                            if '(' in receiver:
                                if all(town not in receiver for town in towns_list) and ('서울특별시' in receiver):
                                    # Change the key to the new one
                                    if key not in filtered_edges_dict.keys():
                                        filtered_edges_dict[key] = {}
                                    filtered_edges_dict[key][(sender, dept1)] = count
                                    total_count += 1
                            else:
                                if key not in filtered_edges_dict.keys():
                                    filtered_edges_dict[key] = {}
                                filtered_edges_dict[key][(sender, dept1)] = count
                                total_count += 1

        #print("total count of filtered docs: " + str(total_count))
        #print(filtered_edges_dict)
        return filtered_edges_dict

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
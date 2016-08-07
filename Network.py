import networkx as nx
import matplotlib.pyplot as plt
import os
import matplotlib.font_manager as fm

class Network():
    def __init__(self, edges):
        self.edges = edges

    ### weight도 포함된 데이터를 보내야 되나
    def make_graph(self, policy_id, month, policy_title):
        print("Now: " + policy_id + ", " + month)
        # self.edges is a dictionary
        edges = []
        for edge, count in self.edges.items():
            # Transform dictionary into tuples with three elements (source, target, weight)
            print(edge[0], edge[1], count)
            edges.append((edge[0], edge[1], count))

        fp1 = fm.FontProperties(
            fname="./NotoSansCJKkr-Regular.otf")  # Free Font https://www.google.com/get/noto/pkgs/NotoSansKorean-windows.zip
        nx.set_fontproperties(fp1)

        G = nx.DiGraph()
        G.add_weighted_edges_from(edges)

        graph_pos = nx.spring_layout(G)

        weights = [ weight/2 for (source, target, weight) in edges ]

        # we can now added edge thickness and edge color
        nx.draw_networkx_edges(G, graph_pos, width=weights, alpha=1, edge_color='black')
        nx.draw_networkx_nodes(G, graph_pos, node_size=100, node_color='red', alpha=1)
        nx.draw_networkx_labels(G, graph_pos, font_size=8)

        #plt.show()
        #f = plt.figure()
        policy_folder_name = policy_id + "_" + policy_title.replace(" ","").replace("/","").replace("'", "")
        os.system("mkdir './graphs_for_policy/%s'" % policy_folder_name)
        plt.axis('off')
        plt.savefig("./graphs_for_policy/%s/%s.png" % (policy_folder_name, month), bbox_inches="tight")
        plt.clf()
        G.clear()






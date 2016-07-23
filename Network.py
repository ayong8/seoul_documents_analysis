import networkx as nx
import matplotlib.pyplot as plt

class Network():
    def __init__(self, edges):
        self.edges = edges

    ### weight도 포함된 데이터를 보내야 되나
    def make_graph(self):
        G = nx.DiGraph()

        G.add_edges_from(self.edges)

        graph_pos = nx.shell_layout(G)

        # draw nodes, edges and labels
        nx.draw_networkx_nodes(G, graph_pos, node_size=1000, node_color='blue', alpha=0.3)
        # we can now added edge thickness and edge color
        nx.draw_networkx_edges(G, graph_pos, width=2, alpha=0.3, edge_color='green')
        nx.draw_networkx_labels(G, graph_pos, font_size=12, font_family='sans-serif')

        plt.show()






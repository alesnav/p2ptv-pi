#Embedded file name: ACEStream\Core\CacheDB\maxflow.pyo
from copy import deepcopy

class Network(object):
    __slots__ = ['arcs',
     'backarcs',
     'nodes',
     'labels']

    def __init__(self, arcs):
        self.nodes = []
        self.labels = {}
        self.arcs = arcs
        self.backarcs = {}
        for source in arcs:
            if source not in self.nodes:
                self.nodes.append(source)
            if source not in self.backarcs:
                self.backarcs[source] = {}
            for dest in arcs[source]:
                if dest not in self.nodes:
                    self.nodes.append(dest)
                if dest not in self.backarcs:
                    self.backarcs[dest] = {}
                self.backarcs[dest][source] = {'cap': arcs[source][dest]['cap'],
                 'flow': 0}

    def min(a, b):
        if a == -1:
            return b
        if b == -1:
            return a
        return min(a, b)

    min = staticmethod(min)

    def maxflow(self, source, sink, max_distance = 10000):
        if source not in self.nodes or sink not in self.nodes:
            return 0.0
        arcscopy = deepcopy(self.arcs)
        backarcscopy = deepcopy(self.backarcs)
        DEBUG = False
        while 1:
            labels = {}
            labels[source] = ((0, 0), -1)
            unscanned = {source: 0}
            scanned = set()
            while 1:
                for node in unscanned:
                    if DEBUG:
                        print 'Unscanned: ' + str(node)
                    for outnode in arcscopy[node]:
                        if DEBUG:
                            print 'to ', outnode
                        if outnode in unscanned or outnode in scanned:
                            continue
                        arc = arcscopy[node][outnode]
                        if arc['flow'] >= arc['cap'] or unscanned[node] + 1 > max_distance:
                            continue
                        labels[outnode] = ((node, 1), Network.min(labels[node][1], arc['cap'] - arc['flow']))
                        if DEBUG:
                            print labels[outnode]
                        unscanned[outnode] = unscanned[node] + 1

                    for innode in backarcscopy[node]:
                        if DEBUG:
                            print 'from ', innode
                        if innode in unscanned or innode in scanned:
                            continue
                        arc = arcscopy[innode][node]
                        if arc['flow'] == 0 or unscanned[node] + 1 > max_distance:
                            continue
                        labels[innode] = ((node, -1), Network.min(labels[node][1], arc['flow']))
                        if DEBUG:
                            print labels[innode]
                        unscanned[innode] = unscanned[node] + 1

                    del unscanned[node]
                    scanned.add(node)
                    break
                else:
                    sum = 0
                    for innode in backarcscopy[sink]:
                        sum += arcscopy[innode][sink]['flow']

                    return sum

                if sink in unscanned:
                    break

            s = sink
            (node, sense), et = labels[s]
            while 1:
                if s == source:
                    break
                (node, sense), epi = labels[s]
                if sense == 1:
                    arcscopy[node][s]['flow'] += et
                else:
                    arcscopy[s][node]['flow'] -= et
                s = node


if __name__ == '__main__':
    n = Network({'s': {'a': {'cap': 20,
                 'flow': 0},
           'x': {'cap': 1,
                 'flow': 0},
           'y': {'cap': 3,
                 'flow': 0}},
     'x': {'y': {'cap': 1,
                 'flow': 0},
           't': {'cap': 3,
                 'flow': 0}},
     'y': {'x': {'cap': 1,
                 'flow': 0},
           't': {'cap': 1,
                 'flow': 0}},
     'a': {'b': {'cap': 20,
                 'flow': 0}},
     'b': {'c': {'cap': 20,
                 'flow': 0}},
     'c': {'t': {'cap': 20,
                 'flow': 0}}})
    print n.nodes
    print n.maxflow('s', 'q', max_distance=2)

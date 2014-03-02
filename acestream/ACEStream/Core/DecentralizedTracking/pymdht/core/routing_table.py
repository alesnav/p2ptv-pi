#Embedded file name: ACEStream\Core\DecentralizedTracking\pymdht\core\routing_table.pyo
import ptime as time
import logging
logger = logging.getLogger('dht')

class PopError(Exception):
    pass


class PutError(Exception):
    pass


class SuperBucket(object):

    def __init__(self, index, max_nodes):
        self.index = index
        self.main = Bucket(max_nodes)
        self.replacement = Bucket(max_nodes)


class Bucket(object):

    def __init__(self, max_rnodes):
        self.max_rnodes = max_rnodes
        self.rnodes = []
        self.last_maintenance_ts = time.time()
        self.last_changed_ts = 0

    def get_rnode(self, node_):
        i = self._find(node_)
        if i >= 0:
            return self.rnodes[i]

    def add(self, rnode):
        rnode.bucket_insertion_ts = time.time()
        self.rnodes.append(rnode)

    def remove(self, node_):
        del self.rnodes[self._find(node_)]

    def __repr__(self):
        return '\n'.join(['b>'] + [ repr(rnode) for rnode in self.rnodes ])

    def __len__(self):
        return len(self.rnodes)

    def __eq__(self, other):
        if self.max_rnodes != other.max_rnodes or len(self) != len(other):
            return False
        for self_rnode, other_rnode in zip(self.rnodes, other.rnodes):
            if self_rnode != other_rnode:
                return False

        return True

    def __ne__(self, other):
        return not self == other

    def there_is_room(self, min_places = 1):
        return len(self.rnodes) + min_places <= self.max_rnodes

    def get_freshest_rnode(self):
        freshest_ts = 0
        freshest_rnode = None
        for rnode in self.rnodes:
            if rnode.last_seen > freshest_ts:
                freshest_ts = rnode.last_seen
                freshest_rnode = rnode

        return freshest_rnode

    def get_stalest_rnode(self):
        oldest_ts = time.time()
        stalest_rnode = None
        for rnode in self.rnodes:
            if rnode.last_seen < oldest_ts:
                oldest_ts = rnode.last_seen
                stalest_rnode = rnode

        return stalest_rnode

    def sorted_by_rtt(self):
        return sorted(self.rnodes, key=lambda x: x.rtt)

    def _find(self, node_):
        for i, rnode in enumerate(self.rnodes):
            if rnode == node_:
                return i

        return -1


NUM_SBUCKETS = 160
NUM_NODES = 8

class RoutingTable(object):

    def __init__(self, my_node, nodes_per_bucket):
        self.my_node = my_node
        self.nodes_per_bucket = nodes_per_bucket
        self.sbuckets = [None] * NUM_SBUCKETS
        self.num_rnodes = 0
        self.lowest_index = NUM_SBUCKETS

    def get_sbucket(self, log_distance):
        index = log_distance
        if index < 0:
            raise IndexError, 'index (%d) must be >= 0' % index
        sbucket = self.sbuckets[index]
        if not sbucket:
            sbucket = SuperBucket(index, self.nodes_per_bucket[index])
            self.sbuckets[index] = sbucket
        return sbucket

    def update_lowest_index(self, index):
        if index < self.lowest_index:
            sbucket = self.sbuckets[index]
            if sbucket and sbucket.main:
                self.lowest_index = sbucket.index
            return
        if index == self.lowest_index:
            for i in range(index, NUM_SBUCKETS):
                sbucket = self.sbuckets[i]
                if sbucket and sbucket.main:
                    self.lowest_index = i
                    return

            self.lowest_index = NUM_SBUCKETS

    def get_closest_rnodes(self, log_distance, max_rnodes, exclude_myself):
        result = []
        index = log_distance
        for i in range(index, self.lowest_index - 1, -1):
            sbucket = self.sbuckets[i]
            if not sbucket:
                continue
            result.extend(sbucket.main.rnodes[:max_rnodes - len(result)])
            if len(result) == max_rnodes:
                return result

        if not exclude_myself:
            result.append(self.my_node)
        for i in range(index + 1, NUM_SBUCKETS):
            sbucket = self.sbuckets[i]
            if not sbucket:
                continue
            result.extend(sbucket.main.rnodes[:max_rnodes - len(result)])
            if len(result) == max_rnodes:
                break

        return result

    def find_next_bucket_with_room_index(self, node_ = None, log_distance = None):
        index = log_distance or node_.log_distance(self.my_node)
        for i in range(index + 1, NUM_SBUCKETS):
            sbucket = self.sbuckets[i]
            if sbucket is None or self.sbuckets[i].main.there_is_room():
                return i

    def get_main_rnodes(self):
        rnodes = []
        for i in range(self.lowest_index, NUM_SBUCKETS):
            sbucket = self.sbuckets[i]
            if sbucket:
                rnodes.extend(sbucket.main.rnodes)

        return rnodes

    def print_stats(self):
        num_nodes = 0
        for i in range(self.lowest_index, NUM_SBUCKETS):
            sbucket = self.sbuckets[i]
            if sbucket and len(sbucket.main):
                print i, len(sbucket.main), len(sbucket.replacement)

        print 'Total:', self.num_rnodes

    def __repr__(self):
        begin = ['==============RoutingTable============= BEGIN']
        data = [ '%d %r' % (i, sbucket) for i, sbucket in enumerate(self.sbuckets) ]
        end = ['==============RoutingTable============= END']
        return '\n'.join(begin + data + end)

import heapq

#### Tuple
class TupleMaxHeap:
    def __init__(self, count=2):
        self.heap = [];
        self.count = count
    def push(self, x):
        heapq.heappush(self.heap, (-x[0], *[x[i] for i in range(1, self.count)]));
    def pop(self):
        x = heapq.heappop(self.heap); return (-x[0], *[x[i] for i in range(1, self.count)]);
    def __getitem__(self, i):
        x = self.heap[i]; return (-x[0], *[x[i] for i in range(1, self.count)]);
    def __len__(self): return len(self.heap);
    def __repr__(self):
        s = "["
        for i in range(len(self)):
            s += str(self[i])
            if i < len(self) - 1: s += ", "
        return s + "]"

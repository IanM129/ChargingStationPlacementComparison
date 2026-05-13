import math

#### 2 dimensional
class Vector2:
    def __init__(self, x, y):
        self.x = x; self.y = y;
    def __getitem__(self, i):
        if (i == 0): return self.x;
        if (i == 1): return self.y;
        raise IndexError(f'list index out of range: {i} / 2');
    def __len__(self): return 2;
    def magnitude(self):
        return math.sqrt(pow(self.x, 2) + pow(self.y, 2));
    def normalized(self):
        length = self.magnitude();
        return (self.x / length, self.y / length);
def normalizeVector(x : float, y : float):
    length = math.sqrt(pow(x, 2) + pow(y, 2))
    return (x / length, y / length)

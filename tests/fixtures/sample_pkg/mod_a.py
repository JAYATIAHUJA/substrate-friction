def helper(x):
    if x > 0:
        return x
    return -x


class Widget:
    def render(self, x):
        return helper(x)

    def draw(self, x):
        for i in range(x):
            if i % 2:
                continue
        return self.render(x)

from mod_a import Widget, helper


class FancyWidget(Widget):
    def render(self, x):
        return helper(x) + 1


def build(x):
    return FancyWidget().render(x)

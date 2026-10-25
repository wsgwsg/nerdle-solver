import json
import itertools
import math


class MathWordleGenerator:
    def __init__(self, target_length=12):
        self.target_length = target_length
        self.patterns = set()  # 自动去重
        self.count = 0

    def evaluate(self, a, op, b):
        """安全的计算函数，处理除零、浮点数和超限问题"""
        if op == "/" and b == 0:
            return None
        res = a * b if op == "*" else a // b if op == "/" else a + b if op == "+" else a - b

        if op == "/" and a % b != 0:
            return None  # 只保留能整除的结果
        return res

    def evaluate_expression(self, values, operators, max_intermediate):
        """按标准优先级计算表达式：先乘除，后加减。"""
        terms = []
        low_precedence_ops = []
        current = values[0]

        for value, op in zip(values[1:], operators):
            if op in ("*", "/"):
                current = self.evaluate(current, op, value)
                if current is None or abs(current) > max_intermediate:
                    return None
            else:
                terms.append(current)
                low_precedence_ops.append(op)
                current = value
        terms.append(current)

        result = terms[0]
        for term, op in zip(terms[1:], low_precedence_ops):
            result = self.evaluate(result, op, term)
            if result is None or abs(result) > max_intermediate:
                return None
        return result

    def apply_question_mark(self, val):
        """将数字的个位替换为 '?'"""
        s = str(val)
        return s[:-1] + "?" if len(s) > 1 else "?"

    # ------------------------------------------------------------------
    # 区间可行性剪枝
    # ------------------------------------------------------------------
    @staticmethod
    def _interval_add(a, b):
        return a[0] + b[0], a[1] + b[1]

    @staticmethod
    def _interval_sub(a, b):
        return a[0] - b[1], a[1] - b[0]

    @staticmethod
    def _interval_mul(a, b):
        values = (a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1])
        return min(values), max(values)

    @staticmethod
    def _interval_div(a, b):
        """正整数操作数区间除法（分母为正）。"""
        if b[0] <= 0:
            return -(10**18), 10**18
        if a[0] >= 0:
            return a[0] // b[1], a[1] // b[0]
        if a[1] <= 0:
            return a[0] // b[0], a[1] // b[1]
        negative_lo = a[0] // b[0]
        negative_hi = -1 // b[1]
        positive_lo = 0
        positive_hi = a[1] // b[0]
        return min(negative_lo, positive_lo), max(negative_hi, positive_hi)

    def _interval_op(self, a, op, b):
        if op == "+":
            return self._interval_add(a, b)
        if op == "-":
            return self._interval_sub(a, b)
        if op == "*":
            return self._interval_mul(a, b)
        return self._interval_div(a, b)

    @staticmethod
    def _interval_has_answer(interval, answer_length, max_inter):
        """区间内是否存在“字符串长度恰好为 answer_length”的合法答案。"""
        lo, hi = interval
        positive_lo = 0 if answer_length == 1 else 10 ** (answer_length - 1)
        positive_hi = min(10**answer_length - 1, max_inter)
        if positive_lo <= positive_hi and max(lo, positive_lo) <= min(hi, positive_hi):
            return True

        if answer_length >= 2:
            negative_lo = max(-max_inter, -(10 ** (answer_length - 1) - 1))
            negative_hi = -(10 ** (answer_length - 2))
            if negative_lo <= negative_hi and max(lo, negative_lo) <= min(hi, negative_hi):
                return True
        return False

    # ------------------------------------------------------------------
    # 答案枚举 / 反解某一个操作数
    # ------------------------------------------------------------------
    @staticmethod
    def _count_answers(answer_length, max_inter):
        if answer_length == 1:
            return min(10, max_inter + 1)
        positive_lo = 10 ** (answer_length - 1)
        positive_hi = min(10**answer_length - 1, max_inter)
        positive = max(0, positive_hi - positive_lo + 1)
        negative_lo = 10 ** (answer_length - 2)
        negative_hi = min(10 ** (answer_length - 1) - 1, max_inter)
        negative = max(0, negative_hi - negative_lo + 1)
        return positive + negative

    @staticmethod
    def _answer_values(answer_length, max_inter):
        if answer_length == 1:
            for value in range(0, min(9, max_inter) + 1):
                yield value
            return
        positive_hi = min(10**answer_length - 1, max_inter)
        for value in range(10 ** (answer_length - 1), positive_hi + 1):
            yield value
        negative_hi = min(10 ** (answer_length - 1) - 1, max_inter)
        for magnitude in range(10 ** (answer_length - 2), negative_hi + 1):
            yield -magnitude

    # ------------------------------------------------------------------
    # 表达式树（2/3/4 操作数通用）：区间、反解
    # ------------------------------------------------------------------
    @staticmethod
    def _build_tree(op_combo):
        """按标准优先级把操作数表达式建成二叉树，叶子是操作数下标。"""
        terms = []
        low_ops = []
        current = 0
        for index, op in enumerate(op_combo):
            next_leaf = index + 1
            if op in "*/":
                current = (op, current, next_leaf)
            else:
                terms.append(current)
                low_ops.append(op)
                current = next_leaf
        terms.append(current)
        tree = terms[0]
        for op, term in zip(low_ops, terms[1:]):
            tree = (op, tree, term)
        return tree

    def _tree_contains(self, node, index):
        if isinstance(node, int):
            return node == index
        return self._tree_contains(node[1], index) or self._tree_contains(node[2], index)

    def _eval_tree(self, node, values, max_inter):
        if isinstance(node, int):
            return values[node]
        left = self._eval_tree(node[1], values, max_inter)
        if left is None:
            return None
        right = self._eval_tree(node[2], values, max_inter)
        if right is None:
            return None
        result = self.evaluate(left, node[0], right)
        if result is None or abs(result) > max_inter:
            return None
        return result

    def _interval_tree(self, node, bounds):
        if isinstance(node, int):
            return bounds[node]
        return self._interval_op(
            self._interval_tree(node[1], bounds),
            node[0],
            self._interval_tree(node[2], bounds),
        )

    @staticmethod
    def _tree_invert_left(op, right, target):
        """已知右子节点，求左子节点。"""
        if op == "+":
            return target - right
        if op == "-":
            return target + right
        if op == "*":
            if right == 0:
                return 0 if target == 0 else None
            if target % right == 0:
                return target // right
            return None
        return target * right

    @staticmethod
    def _tree_invert_right(op, left, target):
        """已知左子节点，求右子节点。"""
        if op == "+":
            return target - left
        if op == "-":
            return left - target
        if op == "*":
            if left == 0:
                return 0 if target == 0 else None
            if target % left == 0:
                return target // left
            return None
        if target == 0:
            return None
        if left % target == 0:
            return left // target
        return None

    def _invert_tree(self, node, index, values, target, max_inter):
        if isinstance(node, int):
            return target if node == index else None
        op, left, right = node
        if self._tree_contains(left, index):
            right_value = self._eval_tree(right, values, max_inter)
            if right_value is None:
                return None
            new_target = self._tree_invert_left(op, right_value, target)
            if new_target is None:
                return None
            return self._invert_tree(left, index, values, new_target, max_inter)

        left_value = self._eval_tree(left, values, max_inter)
        if left_value is None:
            return None
        new_target = self._tree_invert_right(op, left_value, target)
        if new_target is None:
            return None
        return self._invert_tree(right, index, values, new_target, max_inter)

    def _group_is_feasible(self, tree, group, answer_length, max_inter):
        bounds = [(values[0], values[-1]) for values in group]
        return self._interval_has_answer(self._interval_tree(tree, bounds), answer_length, max_inter)

    def _record_equation(
        self,
        nums,
        op_combo,
        var_names,
        replace_q,
        max_inter,
        answer_length,
        expected_ans=None,
    ):
        val = self.evaluate_expression(list(nums), op_combo, max_inter)
        if val is None or abs(val) > max_inter:
            return
        if expected_ans is not None and val != expected_ans:
            return
        if len(str(val)) != answer_length:
            return

        self.count += 1
        vars_dict = dict(zip(var_names, nums))
        vars_dict[self.ans_name] = val
        self.patterns.add(self.create_pattern(var_names, vars_dict, op_combo, replace_q))
        if self.count % 1000000 == 0:
            print(f"  已处理 {self.count} 个等式，去重后模式: {len(self.patterns)}")

    def _pruned_group_entries(self, ranges):
        """按数字字符串长度分组，返回 (长度组合, 答案长度, 操作数列表)。

        answer_length 是答案字符串的长度（负数包含 '-'）。
        """
        value_groups = []
        for start, end in ranges:
            groups = {}
            for value in range(start, end + 1):
                groups.setdefault(len(str(value)), []).append(value)
            value_groups.append(groups)

        # n 个操作数之间有 n - 1 个运算符，另有一个等号。
        separator_count = len(ranges)
        target_operand_length = self.target_length - separator_count
        entries = []
        for length_combo in itertools.product(*[tuple(groups) for groups in value_groups]):
            answer_length = target_operand_length - sum(length_combo)
            if answer_length < 1:
                continue

            entries.append(
                (
                    length_combo,
                    answer_length,
                    tuple(value_groups[index][length] for index, length in enumerate(length_combo)),
                )
            )
        return entries

    def _pruned_value_groups(self, ranges):
        """按数字字符串长度分组，只返回可能组成目标长度的操作数。"""
        return [group for _, _, group in self._pruned_group_entries(ranges)]

    def generate(self, config):
        """
        根据配置生成等式
        config: dict, 包含:
            - name: 格式名称
            - ops: list of list, 操作符列表，例如 [['*', '/'], ['+', '-']]
            - ranges: list of tuple, 对应 A, B, C 等变量的取值范围
            - replace_q: list of str, 哪些变量需要替换个位为 '?' 例如 ['C', 'D']
            - max_intermediate: int, 中间结果的最大值（用于剪枝）
        """
        print(f"正在处理 {config['name']}...")
        ops = config["ops"]
        ranges = config["ranges"]
        replace_q = config["replace_q"]
        max_inter = config.get("max_intermediate", 99999)

        # 变量名序列 (A, B, C...)
        var_names = [chr(65 + i) for i in range(len(ranges))]
        self.ans_name = chr(65 + len(ranges))
        count = len(ranges)
        group_entries = self._pruned_group_entries(ranges)
        print(f"  经过长度剪枝后，可能的操作数组合数量: {len(group_entries)}")
        if count in (2, 3, 4):
            total = 0
            for _, _, group in group_entries:
                product = 1
                for values in group:
                    product *= len(values)
                total += product
            unit = {2: "二元组", 3: "三元组", 4: "四元组"}[count]
            print(f"  长度剪枝后{unit}总数: {total:,}（随后会按区间和答案反解继续缩减）")

        # 2/3/4 个正操作数统一走表达式树：区间剪枝 + 反解任意一个操作数。
        # 含 0/负数的范围退回原来的穷举逻辑。
        optimized = count in (2, 3, 4) and all(start >= 1 for start, _ in ranges)

        for op_combo in itertools.product(*ops):
            use_optimized = optimized and len(op_combo) == count - 1
            tree = self._build_tree(op_combo) if use_optimized else None
            for lengths, answer_length, group in group_entries:
                if not use_optimized:
                    self._generate_direct_group(group, op_combo, var_names, replace_q, max_inter, answer_length)
                    continue

                if not self._group_is_feasible(tree, group, answer_length, max_inter):
                    continue

                answer_count = self._count_answers(answer_length, max_inter)
                if answer_count <= 0:
                    continue

                sizes = [len(values) for values in group]
                direct_cost = 1
                for size in sizes:
                    direct_cost *= size

                best_index = -1
                best_cost = direct_cost
                for index in range(count):
                    cost = answer_count
                    for other in range(count):
                        if other != index:
                            cost *= sizes[other]
                    if cost < best_cost:
                        best_cost = cost
                        best_index = index

                if best_index < 0:
                    self._generate_direct_group(group, op_combo, var_names, replace_q, max_inter, answer_length)
                else:
                    self._generate_solve_group(
                        tree,
                        group,
                        lengths,
                        ranges,
                        best_index,
                        op_combo,
                        var_names,
                        replace_q,
                        max_inter,
                        answer_length,
                    )

    def _generate_direct_group(self, group, op_combo, var_names, replace_q, max_inter, answer_length):
        for nums in itertools.product(*group):
            self._record_equation(nums, op_combo, var_names, replace_q, max_inter, answer_length)

    def _generate_solve_group(
        self,
        tree,
        group,
        lengths,
        ranges,
        index,
        op_combo,
        var_names,
        replace_q,
        max_inter,
        answer_length,
    ):
        """固定其余操作数和答案，反解第 index 个操作数；2/3/4 操作数共用。"""
        count = len(group)
        other = [i for i in range(count) if i != index]
        values = [None] * count
        start, end = ranges[index]
        answers = list(self._answer_values(answer_length, max_inter))
        for combo in itertools.product(*[group[i] for i in other]):
            for position, value in zip(other, combo):
                values[position] = value
            for ans in answers:
                target = self._invert_tree(tree, index, values, ans, max_inter)
                if target is None or not (start <= target <= end):
                    continue
                if len(str(target)) != lengths[index]:
                    continue
                values[index] = target
                self._record_equation(
                    tuple(values),
                    op_combo,
                    var_names,
                    replace_q,
                    max_inter,
                    answer_length,
                    expected_ans=ans,
                )

    def create_pattern(self, var_names, vars_dict, op_combo, replace_q):
        """根据变量字典和替换规则生成最终的 pattern 字符串"""
        display_vars = {}
        for v in var_names + [self.ans_name]:
            if v in replace_q:
                display_vars[v] = self.apply_question_mark(vars_dict[v])
            else:
                display_vars[v] = str(vars_dict[v])

        pat = f"{display_vars['A']}{op_combo[0]}{display_vars['B']}"
        if len(var_names) == 3:
            pat += f"{op_combo[1]}{display_vars['C']}"
        if len(var_names) == 4:
            pat += f"{op_combo[1]}{display_vars['C']}{op_combo[2]}{display_vars['D']}"
        pat += f"={display_vars[self.ans_name]}"
        return pat

    def save(self, filename="solutions_optimized.json"):
        if not self.patterns:
            print("⚠️ 没有生成任何模式，可能是配置或范围过于严格。")
            return

        print(f"\n生成完成！共遍历了 {self.count} 个有效等式，去重后剩余 {len(self.patterns)} 个模式。")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(list(self.patterns), f, ensure_ascii=False, indent=0)
        print(f"成功保存至 {filename}")
        self.patterns.clear()


if __name__ == "__main__":
    # ==========================
    # 定义你的各种格式配置
    # ==========================
    configs = {
        2: [
            {
                "name": "格式 1: A +- B = C (A,B ∈ [1, 99999])",
                "ops": [["+", "-"]],
                "ranges": [(1, 99999), (1, 99999)],
                "replace_q": ["A", "B", "C"],
            },
            {
                "name": "格式 2: A op B = C (A,B ∈ [1, 99999])",
                "ops": [["*", "/"]],
                "ranges": [(1, 99999), (1, 99999)],
                "replace_q": [],
            },
        ],
        3: [
            {
                "name": "格式 1: A op B +- C = D (A,B,C ∈ [1, 9999])",
                "ops": [["*", "/"], ["+", "-"]],  # 第一层(* /), 第二层(+ -)
                "ranges": [(1, 9999), (1, 9999), (1, 9999)],  # A, B, C 的范围
                "replace_q": ["C", "D"],  # 将 C 和 D 的个位替换为 ?
            },
            {
                "name": "格式 2: A +- B op C = D (A,B,C ∈ [1, 9999])",
                "ops": [["+", "-"], ["*", "/"]],
                "ranges": [(1, 9999), (1, 9999), (1, 9999)],
                "replace_q": ["A", "D"],  # 将 A 和 D 的个位替换为 ?
            },
            {
                "name": "格式 3: A +- B +- C = D (A,B,C ∈ [1, 9999])",
                "ops": [["+", "-"], ["+", "-"]],
                "ranges": [(1, 9999), (1, 9999), (1, 9999)],
                "replace_q": ["A", "B", "C", "D"],  # 全替换个位
            },
            {
                "name": "格式 4: A */ B */ C = D (A,B,C ∈ [1, 9999])",
                "ops": [["*", "/"], ["*", "/"]],
                "ranges": [(1, 9999), (1, 9999), (1, 9999)],
                "replace_q": [],  # 乘除法不替换
            },
        ],
        4: [
            {
                "name": "格式 1: A +- B +- C +- D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["+", "-"], ["+", "-"], ["+", "-"]],
                "ranges": [(1, 999), (1, 999), (1, 999), (1, 999)],
                "replace_q": ["A", "B", "C", "D", "E"],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
            {
                "name": "格式 2: A +- B +- C op D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["+", "-"], ["+", "-"], ["*", "/"]],
                "ranges": [(1, 999), (1, 999), (1, 6561), (1, 999)],
                "replace_q": ["A", "B", "E"],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
            {
                "name": "格式 3: A +- B op C +- D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["+", "-"], ["*", "/"], ["+", "-"]],
                "ranges": [(1, 999), (1, 6561), (1, 999), (1, 999)],
                "replace_q": ["A", "D", "E"],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
            {
                "name": "格式 4: A +- B op C op D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["+", "-"], ["*", "/"], ["*", "/"]],
                "ranges": [(1, 999), (1, 6561), (1, 999), (1, 999)],
                "replace_q": ["A", "E"],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
            {
                "name": "格式 5: A op B +- C +- D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["*", "/"], ["+", "-"], ["+", "-"]],
                "ranges": [(1, 6561), (1, 999), (1, 999), (1, 999)],
                "replace_q": ["C", "D", "E"],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
            {
                "name": "格式 6: A op B +- C op D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["*", "/"], ["+", "-"], ["*", "/"]],
                "ranges": [(1, 999), (1, 999), (1, 999), (1, 999)],
                "replace_q": [],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
            {
                "name": "格式 7: A op B op C +- D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["*", "/"], ["*", "/"], ["+", "-"]],
                "ranges": [(1, 6561), (1, 999), (1, 999), (1, 999)],
                "replace_q": ["D", "E"],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
            {
                "name": "格式 8: A op B op C op D = E (A,B,C,D ∈ [1, 999])",
                "ops": [["*", "/"], ["*", "/"], ["*", "/"]],
                "ranges": [(1, 6561), (1, 999), (1, 999), (1, 999)],
                "replace_q": [],
                "max_intermediate": 9999,  # 限制中间结果最大值，避免过大
            },
        ],
    }

    length = 8  # 目标等式长度

    # 运行生成器
    generator = MathWordleGenerator(target_length=length)

    for ops, config_group in configs.items():
        for config in config_group:
            print(f"\n正在生成 {config['name']}...")
            generator.generate(config)

        generator.save(f"solutions_format{ops}_{length}.json")

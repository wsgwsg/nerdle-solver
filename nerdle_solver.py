import bisect
import itertools
import json
import math
import os
import random
import re


class MathWordleSolver:
    def __init__(self, json_files, length=12):
        self.all_candidates = set()
        self.remaining_candidates = set()
        self.positive_chars = set()
        self.gray_chars = set()
        self.yellow_positions = {}
        self.length = length
        self.last_answer_sample = []
        self.last_scores = {}
        self.last_wildcard_scores = []
        self.load_data(json_files)
        self.reset()

    def load_data(self, json_files):
        """加载多个 JSON 文件并合并数据"""
        for file in json_files:
            if os.path.exists(file):
                print(f"正在加载: {file}")
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.all_candidates.update(data)
            else:
                print(f"⚠️ 警告: 找不到文件 {file}")
        print(f"✅ 数据加载完成，共载入 {len(self.all_candidates)} 个候选等式。")

    def reset(self):
        """重置游戏状态，恢复全量数据"""
        self.remaining_candidates = self.all_candidates.copy()
        self.positive_chars.clear()
        self.gray_chars.clear()
        self.yellow_positions.clear()
        self.last_answer_sample = []
        self.last_scores = {}
        self.last_wildcard_scores = []
        print(f"🔄 状态已重置。当前剩余候选数: {len(self.remaining_candidates)}")

    def get_wordle_feedback(self, guess, answer):
        """计算 guess 针对 answer 的 Wordle 反馈 (G, Y, X)"""
        feedback = ["X"] * self.length
        answer_chars = list(answer)

        # 绿色 (G)
        for i in range(self.length):
            if guess[i] == answer_chars[i]:
                feedback[i] = "G"
                answer_chars[i] = None

        # 黄色 (Y)
        for i in range(self.length):
            if feedback[i] == "X":
                if guess[i] in answer_chars:
                    feedback[i] = "Y"
                    answer_chars[answer_chars.index(guess[i])] = None

        return "".join(feedback)

    # ------------------------------------------------------------------
    # 候选排序
    #
    # 参考 pedrokkrause/Nerdle-Equations 的 wordle.py：
    # 对猜测 g，按 feedback 把当前答案集合分成若干桶，用
    # H(g) = -Σ p log2(p) 排序（越大越好）。
    # 通配符 pattern 没有唯一 feedback，用随机实例化后的平均 H 估算。
    # ------------------------------------------------------------------
    @staticmethod
    def _entropy(counts, total):
        if total <= 0:
            return 0.0
        result = 0.0
        for count in counts.values():
            probability = count / total
            result -= probability * math.log2(probability)
        return result

    @staticmethod
    def _expected_remaining(counts, total):
        """均匀先验下，得到反馈后平均还剩多少个候选。"""
        if total <= 0:
            return 0.0
        return sum(count * count for count in counts.values()) / total

    def _feedback_counts(self, guess, answers):
        counts = {}
        for answer in answers:
            feedback = self.get_wordle_feedback(guess, answer)
            counts[feedback] = counts.get(feedback, 0) + 1
        return counts

    def _instantiate_pattern(self, pattern, rng, max_attempts=100):
        positions = [i for i, char in enumerate(pattern) if char == "?"]
        if not positions:
            return pattern
        for _ in range(max_attempts):
            chars = list(pattern)
            for position in positions:
                chars[position] = str(rng.randrange(10))
            candidate = "".join(chars)
            if self.is_valid_equation(candidate):
                return candidate
        return None

    def _instantiate_pattern_for_feedback(
        self, pattern, guess, feedback, rng, max_attempts=20
    ):
        """按当前 feedback 约束随机实例化 pattern，提高采样命中率。"""
        positions = [i for i, char in enumerate(pattern) if char == "?"]
        if not positions:
            return pattern if self.get_wordle_feedback(guess, pattern) == feedback else None

        choices = []
        for position in positions:
            guessed = guess[position]
            if feedback[position] == "G":
                if not guessed.isdigit():
                    return None
                allowed = guessed
            elif guessed.isdigit():
                allowed = "0123456789".replace(guessed, "")
            else:
                allowed = "0123456789"
            if not allowed:
                return None
            choices.append(allowed)

        for _ in range(max_attempts):
            chars = list(pattern)
            for position, allowed in zip(positions, choices):
                chars[position] = allowed[rng.randrange(len(allowed))]
            candidate = "".join(chars)
            if (
                self.is_valid_equation(candidate)
                and self.get_wordle_feedback(guess, candidate) == feedback
            ):
                return candidate
        return None

    def _sample_answer_pool(self, guess, feedback, exact_answers, sample_size, rng):
        """构造用于算熵的答案样本：精确解 + 通配符随机实例化。"""
        exact_answers = list(dict.fromkeys(exact_answers))
        if sample_size <= 0:
            return exact_answers
        if len(exact_answers) >= sample_size:
            return rng.sample(exact_answers, sample_size)

        answers = exact_answers[:]
        seen = set(answers)
        wildcards = []
        for pattern in self.remaining_candidates:
            if "?" in pattern:
                wildcards.append(pattern)
        if not wildcards:
            return answers

        # 按实例化数量加权，使样本更接近“均匀抽一个具体等式”。
        cumulative_weights = []
        total_weight = 0
        for pattern in wildcards:
            total_weight += 10 ** pattern.count("?")
            cumulative_weights.append(total_weight)

        attempts = 0
        max_attempts = sample_size * 8
        while len(answers) < sample_size and attempts < max_attempts:
            attempts += 1
            pick = rng.random() * total_weight
            index = bisect.bisect_left(cumulative_weights, pick)
            if index >= len(wildcards):
                index = len(wildcards) - 1
            candidate = self._instantiate_pattern_for_feedback(
                wildcards[index], guess, feedback, rng
            )
            if candidate is None or candidate in seen:
                continue
            seen.add(candidate)
            answers.append(candidate)
        return answers

    def _score_candidate(self, candidate, answers, rng, wildcard_samples):
        if "?" not in candidate:
            counts = self._feedback_counts(candidate, answers)
            total = len(answers)
            return (
                self._entropy(counts, total),
                self._expected_remaining(counts, total),
                False,
            )

        entropies = []
        expected = []
        seen = set()
        for _ in range(wildcard_samples):
            instance = self._instantiate_pattern(candidate, rng)
            if instance is None or instance in seen:
                continue
            seen.add(instance)
            counts = self._feedback_counts(instance, answers)
            total = len(answers)
            entropies.append(self._entropy(counts, total))
            expected.append(self._expected_remaining(counts, total))

        if not entropies:
            return 0.0, float(len(answers)), True
        return (
            sum(entropies) / len(entropies),
            sum(expected) / len(expected),
            True,
        )

    def rank_candidates(
        self,
        candidates,
        answers=None,
        wildcard_samples=3,
        seed=20240517,
    ):
        """按估计的 Shannon 熵从高到低排序候选。

        返回 [{'candidate', 'entropy', 'expected_remaining', 'estimated'}]。
        """
        candidates = list(dict.fromkeys(candidates))
        if answers is None:
            answers = self.last_answer_sample
            if not answers:
                answers = [c for c in candidates if "?" not in c]
        answers = list(answers)
        rng = random.Random(seed)
        ranked = []
        for candidate in candidates:
            entropy, expected, estimated = self._score_candidate(
                candidate, answers, rng, wildcard_samples
            )
            ranked.append(
                {
                    "candidate": candidate,
                    "entropy": entropy,
                    "expected_remaining": expected,
                    "estimated": estimated,
                }
            )
        ranked.sort(
            key=lambda item: (
                -item["entropy"],
                item["estimated"],
                item["expected_remaining"],
                item["candidate"],
            )
        )
        return ranked

    def rank_remaining(self, limit=100, wildcard_samples=3, seed=20240517):
        """对当前 remaining_candidates 排序；通配符分数是估算值。"""
        candidates = list(self.remaining_candidates)
        if len(candidates) > limit:
            rng = random.Random(seed)
            candidates = rng.sample(candidates, limit)
        return self.rank_candidates(
            candidates,
            answers=self.last_answer_sample or None,
            wildcard_samples=wildcard_samples,
            seed=seed,
        )

    def is_valid_equation(self, equation):
        """验证具体等式的格式、整数运算和等式结果"""
        if equation.count("=") != 1:
            return False

        expression, result = equation.split("=")
        if (
            not expression
            or not re.fullmatch(r"-?\d+", result)
            or result == "-0"
            or not re.fullmatch(r"[0-9]+(?:[+\-*/][0-9]+)+", expression)
        ):
            return False

        numbers = re.split(r"[+\-*/]", expression)
        operators = re.findall(r"[+\-*/]", expression)
        current = int(numbers[0])
        terms = []
        low_precedence_operators = []
        for index, operator in enumerate(operators):
            right = int(numbers[index + 1])
            if operator == "*":
                current *= right
            elif operator == "/":
                if right == 0 or current % right != 0:
                    return False
                current //= right
            else:
                terms.append(current)
                low_precedence_operators.append(operator)
                current = right
        terms.append(current)

        calculated = terms[0]
        for index, operator in enumerate(low_precedence_operators):
            calculated = (
                calculated + terms[index + 1]
                if operator == "+"
                else calculated - terms[index + 1]
            )

        return calculated == int(result)

    def pattern_matches_feedback(self, pattern, guess, feedback):
        """返回所有能产生反馈的具体等式"""
        matches = []
        question_positions = [i for i, char in enumerate(pattern) if char == "?"]
        if not question_positions:
            if self.is_valid_equation(pattern) and self.get_wordle_feedback(guess, pattern) == feedback:
                matches.append(pattern)
            return matches

        available_digits = [
            digit for digit in "0123456789" if digit not in self.gray_chars
        ]
        # 逐位收窄 '?' 的可选数字：G 固定该位；Y/X 排除猜中的字符；
        # 再叠加已知的黄色位置禁选和灰色字符禁选。
        choices = []
        for position in question_positions:
            guessed = guess[position]
            position_choices = []
            for digit in available_digits:
                if position in self.yellow_positions.get(digit, set()):
                    continue
                if feedback[position] == "G":
                    if digit != guessed:
                        continue
                elif guessed.isdigit() and digit == guessed:
                    continue
                position_choices.append(digit)
            if not position_choices:
                return matches
            choices.append(position_choices)

        # 字符计数快速可行性检查：
        # 若某字符在本轮反馈里有 X，则答案中它的数量恰好等于 G/Y 次数；
        # 否则只要不少于 G/Y 次数。
        fixed_counts = {}
        for char in pattern:
            if char != "?":
                fixed_counts[char] = fixed_counts.get(char, 0) + 1
        colored_counts = {}
        has_gray = set()
        for position, char in enumerate(guess):
            if feedback[position] in ("G", "Y"):
                colored_counts[char] = colored_counts.get(char, 0) + 1
            elif feedback[position] == "X":
                has_gray.add(char)
        for char, required in colored_counts.items():
            fixed = fixed_counts.get(char, 0)
            wildcard_slots = sum(1 for choice in choices if char in choice)
            if char in has_gray:
                if fixed > required or fixed + wildcard_slots < required:
                    return matches
            elif fixed + wildcard_slots < required:
                return matches

        for digits in itertools.product(*choices):
            answer_chars = list(pattern)
            for position, digit in zip(question_positions, digits):
                answer_chars[position] = digit
            exact_answer = "".join(answer_chars)
            if (
                self.is_valid_equation(exact_answer)
                and self.get_wordle_feedback(guess, exact_answer) == feedback
            ):
                matches.append(exact_answer)

        return matches

    def search(
        self,
        guess,
        feedback,
        limit=100,
        rank=True,
        answer_sample=1000,
        wildcard_samples=3,
        wildcard_limit=100,
    ):
        """渐进式查询：基于当前剩余候选池进行筛选。

        rank=True 时按参考仓库的 Shannon 熵从高到低排序；
        通配符 pattern 的分数用随机实例化的平均熵估算。
        """
        if len(guess) != self.length or len(feedback) != self.length:
            return ["输入错误：猜测和反馈的长度必须为 {length}。"]

        feedback = feedback.upper()
        first_filter = []
        new_remaining = []
        matched_results = []
        exact_count = 0

        # 累积反馈的全局约束，用于初筛和通配符展开。
        self.positive_chars.update(
            guess[i] for i in range(self.length) if feedback[i] in ("G", "Y")
        )
        self.gray_chars.update(
            guess[i] for i in range(self.length) if feedback[i] == "X"
        )
        for i in range(self.length):
            if feedback[i] == "Y":
                self.yellow_positions.setdefault(guess[i], set()).add(i)
        self.gray_chars.difference_update(self.positive_chars)

        # ==================== 第一层：快速预筛选 ====================
        for pattern in self.remaining_candidates:
            is_possible = True

            # 1. 检查灰色字符是否出现在不该出现的地方
            if any(c in pattern for c in self.gray_chars):
                continue

            # 2. 基础位置检查 (极快)
            for i in range(self.length):
                if pattern[i] != "?" and i in self.yellow_positions.get(pattern[i], set()):
                    is_possible = False
                    break
                # 如果是绿色，模式对应位置必须是那个字符（或者'?'）
                if feedback[i] == "G":
                    if pattern[i] != "?" and pattern[i] != guess[i]:
                        is_possible = False
                        break
                # 如果是黄色/灰色，模式对应位置不能是该字符（除非是'?'，稍后实例化判断）
                elif feedback[i] in ("Y", "X"):
                    if pattern[i] != "?" and pattern[i] == guess[i]:
                        is_possible = False
                        break

            if not is_possible:
                continue

            first_filter.append(pattern)

        print(f"🔹 初筛后剩余 {len(first_filter)} 个候选模式。")

        # ==================== 第二层：精确实例化与判定 ====================
        for index, pattern in enumerate(first_filter):
            # '?' 代表生成数据中被隐藏的数字，必须尝试其可能的实例化。
            exact_answers = self.pattern_matches_feedback(pattern, guess, feedback)
            if exact_answers:
                new_remaining.extend(exact_answers)
                matched_results.extend(exact_answers)
                exact_count += len(exact_answers)

                # 达到返回上限后，保留尚未精确检查的初筛结果，避免继续进行昂贵的通配符匹配。
                if exact_count >= limit:
                    new_remaining.extend(first_filter[index + 1 :])
                    print(f"⚠️ 已达到返回上限 ({limit} 个)，跳过剩余精确匹配。")
                    break

        # 更新候选池
        self.remaining_candidates = set(new_remaining)
        if rank and matched_results:
            matched_results = list(dict.fromkeys(matched_results))
            rng = random.Random(20240517)
            answers = self._sample_answer_pool(
                guess, feedback, matched_results, answer_sample, rng
            )
            self.last_answer_sample = answers

            # 精确解太多时只对一部分排序，避免排序本身比筛选还慢。
            rank_pool = matched_results
            rank_cap = max(limit, 2000)
            if len(rank_pool) > rank_cap:
                rank_pool = rng.sample(rank_pool, rank_cap)
            ranked = self.rank_candidates(
                rank_pool,
                answers=answers,
                wildcard_samples=wildcard_samples,
                seed=20240517,
            )
            self.last_scores = {item["candidate"]: item for item in ranked}
            matched_results = [item["candidate"] for item in ranked]

            wildcards = [
                pattern for pattern in self.remaining_candidates if "?" in pattern
            ]
            if wildcard_limit > 0 and len(wildcards) > wildcard_limit:
                sampler = random.Random(20240518)
                wildcards = sampler.sample(wildcards, wildcard_limit)
            if wildcard_limit > 0:
                self.last_wildcard_scores = self.rank_candidates(
                    wildcards,
                    answers=answers,
                    wildcard_samples=wildcard_samples,
                    seed=20240518,
                )
            else:
                self.last_wildcard_scores = []
        else:
            self.last_answer_sample = []
            self.last_scores = {}
            self.last_wildcard_scores = []

        if rank:
            return matched_results[:limit]
        return sorted(matched_results)[:limit]


if __name__ == "__main__":
    length = 12  # 固定长度为 12 位
    # 替换为你实际的文件名列表
    files = [f"solutions_format2_{length}.json", f"solutions_format3_{length}.json", f"solutions_format4_{length}.json"]

    solver = MathWordleSolver(files, length=length)

    print("\n=== Math Wordle 渐进式辅助查询器 ===")
    print("说明: G=绿色, Y=黄色, X=灰色。输入 'r' 重置游戏，输入 'q' 退出。\n")

    selected_guess = None
    while True:
        print(f"📌 当前剩余可能解: {len(solver.remaining_candidates)}")
        if selected_guess is not None:
            guess_input = selected_guess
            selected_guess = None
            print(f"已选择候选等式: {guess_input}")
        else:
            guess_input = input(f"请输入你当前的 {length} 位猜测等式 (输入 q 退出, reset 重置): ").strip()

        if guess_input.lower() == "q" or guess_input == "":
            break
        if guess_input.lower() == "r" or guess_input.lower() == "reset":
            solver.reset()
            continue

        feedback_input = input(f"请输入 {length} 位颜色反馈 (G/Y/X): ").strip()
        if feedback_input.lower() == "r" or feedback_input.lower() == "reset":
            solver.reset()
            continue

        # 默认最多显示并寻找 100 个精确解，防止页面卡死
        results = solver.search(guess_input, feedback_input, limit=100)

        print(f"\n🔍 过滤后剩余 {len(solver.remaining_candidates)} 个候选解:")

        # 如果结果太多，只展示前 20 个
        display_limit = 20
        for i, res in enumerate(results[:display_limit]):
            info = solver.last_scores.get(res)
            if info:
                print(
                    f"  {i+1}. {res}  [H={info['entropy']:.3f} bit, "
                    f"E[剩余]≈{info['expected_remaining']:.1f}]"
                )
            else:
                print(f"  {i+1}. {res}")
        if len(results) > display_limit:
            print(f"  ... 还有 {len(results) - display_limit} 个结果未显示")

        # 展示前 10 个通配符候选
        wildcard_scores = solver.last_wildcard_scores[:10]
        if wildcard_scores:
            print("\n🧩 剩余通配符候选（H 为随机实例化估算，仅供排序参考）:")
            for i, item in enumerate(wildcard_scores, 1):
                print(
                    f"  {i}. {item['candidate']}  [H≈{item['entropy']:.3f} bit, "
                    f"E[剩余]≈{item['expected_remaining']:.1f}]"
                )
        print("-" * 50)

        if results:
            selection = input(
                f"请输入候选序号 1-{min(len(results), display_limit)}，"
                "下次直接使用该等式（回车手动输入，q 退出）: "
            ).strip()
            if selection.lower() == "q":
                break
            if selection:
                if len(selection) == length:
                    selected_guess = selection
                try:
                    selection_index = int(selection) - 1
                except ValueError:
                    print("⚠️ 候选序号必须是数字，将在下次循环手动输入。")
                else:
                    if 0 <= selection_index < min(len(results), display_limit):
                        selected_guess = results[selection_index]
                    else:
                        print("⚠️ 候选序号超出范围，将在下次循环手动输入。")

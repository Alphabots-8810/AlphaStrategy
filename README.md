# AlphaStrategy — FRC 策略模拟器（REEFSCAPE 2025 原型）

中文 | [English](README.en.md)

_Last updated: 2026-09-12_ · FRC 8810 Alphabots 出品，属于 Alpha* 系列（[AlphaSim](https://github.com/Alphabots-8810/AlphaSim)、[AlphaScout](https://github.com/Alphabots-8810/AlphaScout)、[AlphaHarness](https://github.com/Alphabots-8810/AlphaHarness)）。

事件驱动的 FRC 比赛模拟器，加上三种求解器：
- **单车精确 DP**：在模拟器自己的随机模型下，求期望 TELEOP 得分的理论最优解，作为 ground truth；
- **CRN rollout 规划器**：处理联盟三车耦合、RP 门槛、胜率这些 DP 算不动的目标。它是实际首选：32 个场景时离 DP 最优差 1.4%，每局约 1 CPU·s；
- **闭环 MCTS**：单车上同样能用，也用 DP 校验过，但要剪枝。达到同样精度，它要花 rollout 约 6 倍的算力；算力加到约 12 倍时，能比 rollout 再接近最优约 0.4 分。联盟层面以 RP 为目标的 MCTS 目前明显落后于启发式，原因还没查清（见"未修"）。

> ⚠️ v0 原型。机器人 profile（cycle 时间、成功率、行驶时间）是**未标定的手设值**，所以绝对分数没有意义，**看差值和灵敏度**。要用于决策，得先接入 scouting 数据来标定。

## 主要发现（前提是模型成立、profile 是占位值）

**1. 在测过的策略里，E[RP] 最高的都是"先赢"型打法；刻意把每层填到门槛的策略反而最低。**

常规赛资格赛，联盟是 elite + mid + l1bot，对手同配置、50% 会配合 coop，400 局全新 seed。最后一列是相对 greedy-net 的配对差值：

| 策略 | P(win) | P(coral RP) | E[RP] | ΔE[RP] vs greedy-net |
|---|---|---|---|---|
| CRN rollout，以得分为目标 | 0.71 | 0.51 | 4.38 | +1.365 ± 0.152 |
| **CRN rollout，以 RP 为目标，z=1 门控** | **0.70** | 0.50 | **4.32** | +1.302 ± 0.143 |
| greedy-proc（藻类全进 processor） | 0.63 | 0.50 | 4.12 | +1.110 ± 0.140 |
| rp-seeker（刻意把每层都填到门槛） | 0.37 | **1.00** | 3.84 | +0.823 ± 0.119 |

rp-seeker 每局都拿到 Coral RP，但少赢的场次让它总 RP 更低。原因是赢一场值 3 RP，远大于一个奖励 RP。

**这个结论能说到哪一步**：
- **以 RP 为目标的 rollout 打法很像 greedy-proc，但这不能当独立证据。** 它把 8.3 个藻类送进 processor，L2 只放 0.7 个，P(coral RP) = P(coop) = 0.50。可它本身就是在 greedy-proc 上做一步前瞻：打平时保留 greedy-proc 的动作，z=1 门控又压住了小幅偏离。所以它像 greedy-proc，有一部分是结构决定的。
- **不带门控的版本确实往 Coral RP 偏了**：P(coral RP) 0.70、L2 放 3.4 个，但 E[RP] 反而掉到 3.91。这说明"一步一步地往 Coral RP 偏"不划算，但不能说明"任何凑 Coral RP 的计划都不划算"。能规划多步、连续填层的更深搜索没有测。
- **前提是 50% 的对手会配合 coop。** 灵敏度 D 节显示，对只管得分的策略来说，没有 coop 几乎拿不到 Coral RP。所以对手越不配合，刻意凑 Coral RP 的相对价值越高。两者在哪个比例交叉，还没测。

**世锦赛那张表为什么大部分行和常规赛一样**：用的是同一批 seed，而且这几个启发式的行为不依赖赛事类型，所以打法完全相同。世锦赛的两个新门槛对它们基本不起作用：
- **Coral RP**：coop 达成时，L1、L3、L4 几乎总是都 ≥ 7。复算 greedy-proc，200 场 coop 里有 198 场如此。所以门槛不管是 5 还是 7，P(coral RP) 都约等于 P(coop)。剩下 2 场有一层停在 6，这正是 greedy-proc 的 P(coral RP) 从 0.50 掉到 0.49 的原因。
- **Barge RP**：barge 总分只有几种可能。elite deep 12（失败就 park 2），mid shallow 6（失败就 park 2），l1bot 只能 park 2。加起来只能是 20、16、10 或 6。复算 greedy-proc 的 400 局，分布是 20 分 272 局、16 分 94 局、10 分 32 局、6 分 2 局，没有一局落在 14–15。所以门槛从 14 提到 16 不影响结果，各行 P(barge RP) 在两张表里都是 0.91–0.92。

明显变化的只有 rp-seeker：E[RP] 从 3.84 掉到 3.54，P(win) 从 0.37 掉到 0.27。其余各行 E[RP] 的变化都不超过 0.04。

**2. Processor 还是 Net，取决于对手 HP 的准度。**
- 看净胜分：对手 HP 投 net 的命中率低于约 68% 时，进 processor 更划算。命中率 50% 时 +6.25 分，75% 时 −2.49 分，68% 是这两点之间的线性插值。
- 看 RP：因为 coop 能降低 Coral RP 门槛，processor 在命中率 75% 时仍然 +0.31 RP，100% 时是 −0.29 RP。转负的点在这两者之间，线性插值约 88%，中间没有测。

**3. 设计优先级。** 单车精确 DP，elite 的 TELEOP 期望分：

| 改进 | ΔV* |
|---|---|
| 行驶时间缩短 10%（动作本身耗时不变） | +5.6 |
| L4 成功率 0.94→0.99 | +2.7 |
| intake 快 0.2 s | +2.2 |
| L4 放置快 0.3 s | +2.1 |
| deep climb 快 1.5 s | +1.2 |
| deep climb 成功率 0.90→0.97 | +0.65 |
| 深笼换浅笼 | −3.9 |
| 完全不处理藻类 | −21.5 |

**4. 联盟里补谁的短板最值。** 以 rp-seeker 为策略，3000 局 CRN：
- l1bot 加 L2：+0.52 RP/场；
- mid 从 shallow 换成 deep climb：+0.52；
- elite 行驶时间缩短 10%：+0.41；
- l1bot 加 shallow climb：+0.17；
- mid 加 L4：≈ 0。

## 快速开始

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q                       # 127 个测试，约 20 s
.venv/bin/python experiments/validate.py            # 单车：DP vs 启发式 vs 规划器（新 seed）
.venv/bin/python experiments/tune_mcts.py --rollouts proc --c 0.5 --prune 0,25 --matches 120 --out results/tune_mcts_prune.md   # MCTS 剪枝对照
.venv/bin/python experiments/tune_mcts.py --rollouts proc --c 0.02,0.05,0.1,0.2,0.5 --prune 0 --matches 120 --out results/tune_mcts_sweep.md   # 无剪枝 MCTS 的 c 扫描
.venv/bin/python experiments/alliance.py --seed-offset 200000   # 联盟：启发式 vs rollout / MCTS
.venv/bin/python experiments/sensitivity.py --dp    # 灵敏度（这是交付物）
.venv/bin/python experiments/tie_rule_ab.py         # rollout 打平规则的影响（教训 5）
results/run_final.sh                                # 重跑 README 引用的全部实验（不含测试；约 1 小时，占满 CPU）
```

## 模型

**规则**（`src/frcsim/reefscape2025/rules.py`）逐条对照 2025 Game Manual（Section 5 V4、Section 6 V13、Section 7 V11）和 Team Update 21 的原文：

| 项目 | 取值 |
|---|---|
| 时长 | AUTO 15 s、TELEOP 135 s |
| 珊瑚分值（AUTO / TELEOP） | L1 3/2、L2 4/3、L3 6/4、L4 7/5 |
| 藻类 | Processor 6、Net 4 |
| Barge | Park 2、Shallow 6、Deep 12 |
| 分支 | L2–L4 每层 12 个，L1（trough）不限量 |
| 持有上限 | 1 珊瑚 + 1 藻类（G409） |
| Coral RP | 常规赛/DCMP 每层 ≥ 5 个；世锦赛 ≥ 7 个（TU21）；Coopertition 达成后降为 3 层 |
| Barge RP | 常规赛 14 分；世锦赛 16 分 |
| Coopertition | 仅资格赛，双方各进 processor ≥ 2 个 |

我们进 processor 的藻类会滚进对方的 Processor Area，对方 HP 可以把它投进**对方自己的** Net 得 4 分。模型把这条耦合保留了下来。

**决策结构**：异步 semi-MDP。某台车做完手上的宏动作就成为 actor，从 `INTAKE / L1–L4 / REM_LOW / REM_HIGH / NET / PROC / FLOOR / CLIMB / PARK` 里选下一个动作。时间用 dt = 0.25 s 的网格。每个动作的耗时 = 行驶 + 服务，建模成一个 lognormal，离散成 k 个等概率原子。模拟器和 DP 读的是**同一张时长表**。

**联盟耦合**（"三车各算 分/秒 再相加"之所以错，就错在这些地方）：
- 2 个 coral station 各自排队，一次只服务一台车；
- processor 同时只能一台车用；
- reef 拥堵：同时在 reef 的车越多，服务时间越长；
- 分支容量和 staged 藻类状态三车共享；
- 地面藻类池共享。

**对手**：v0 没有防守，对手作为外生结果（总分，进 processor 的藻类数）预先采样。它只通过两条路和我们耦合：processor → HP 投 net，以及 Coopertition。对手里 50% 会配合做 coop，所以我们要不要进 processor，得去推断 coop 这一局会不会真的达成。

**AUTO** 按 profile 抽样出结果，不做优化。AUTO 是预先写好的程序，不是一个决策问题。

## 求解器

| 模块 | 做什么 |
|---|---|
| `dp.py` | 单车、期望 TELEOP 分。状态是（位置、持珊瑚、持藻类、#L2、#L3、#L4、剩余低/高藻类），共 562,432 个；在 540 个时间步上逆推，向量化后约 50 s。L1 数量、processor 数量、coop 在这个目标下都不影响最优决策，所以能从状态里去掉。RP 门槛和胜率目标会让状态爆炸，这类目标交给规划器（CRN rollout / MCTS）。 |
| `mcts.py` | 闭环 UCT，带 chance node：子节点用转移后的精确状态做 key。先展开启发式选的动作，可选 progressive bias 和 `action_filter` 剪枝。同一时刻只有刚空闲的那台车做决策，分支数是 \|A\| 而不是 \|A\|³。 |
| `policies.py` | `Greedy`：分/秒贪心 + 残局时间预留，藻类模式 net/proc/coop。<br>`rp_seeker`：追 RP 的变体。<br>**`RolloutPolicy`**：CRN 一步前瞻（Bertsekas rollout），每个候选动作都在同一批随机场景下各跑一遍 base 启发式，取均值最高的。<br>`MCTSPolicy`：对局中每个决策点重新规划；`NoEarlyTerminal` 负责剪枝。 |

五种目标：
- `teleop`：和 DP 同口径；
- `points`：我方得分；
- `margin`：我方减对方，把 processor 送给对面 HP 的分也算进去，是胜率真正单调依赖的连续量；
- `win`：胜率；
- `rp`：期望 RP，季后赛计 0。

`win` 和 `rp` 是离散的，规划时要配 z 门控（见"教训 3"）。

**所有规划器都不能偷看**：场景 seed 来自规划器自己的 RNG。对局有对手时，对手只从规划器自己的 bank 里抽样；有对手却没传 bank，规划时直接报错（`_no_peek`）。单车实验没有对手，不需要 bank。

**随机数与 CRN**：world 模拟里，每个均匀随机数都由 (seed, 机器人, 动作, 第 n 次) 哈希得到，所以不同策略在同一个 seed 上，同类任务遇到的是同样的运气（common random numbers），差值可以用配对 CI 来比。

规划用的克隆同样看不到 world 的未来，但两种规划器的做法不同：
- **CRN rollout**：场景克隆沿用同一套哈希，只是 seed 换成从规划器自己的 RNG 抽出的场景 seed。所以同一场景下各候选动作是配对取数的，教训 5 里的精确打平也由此而来。
- **MCTS**：克隆直接从规划器自己的 `random.Random` 取数。

两者都读不到 world 的 seed。

## 验证

V2–V4 的配置：单车 elite，TELEOP，dt 0.25 s，k 5，藻类遮挡 B，常规赛。V1 是小尺寸实例，全尺寸没法暴力枚举。

| 检查 | 结果 |
|---|---|
| V1：DP = 暴力 expectimax（直接用模拟器自己的转移函数枚举，`tests/test_dp.py`） | 全部在 1e-9 内一致：<br>• dt 0.5 s、k 3、7 s 视界：4 种 profile 的 11 个起始状态 × 藻类解读 A/B，共 22 个用例；<br>• dt 1.0 s、k 2、16 s 视界的 ring buffer 回绕，4 个用例；<br>• 9 s 的残局窗口，1 个用例。 |
| V2：DP 最优策略放回模拟器重放（4000 局） | 108.65 ± 0.19，V* = 108.635 ✅ |
| V3：所有启发式 ≤ V* | greedy-proc −3.37、greedy-coop −11.5、greedy-net −18.0、rp-seeker −22.2 ✅ |

**V4：规划器离最优还差多少**。用新 seed（100000–100199）跑，和调参用的 seed 不重叠。base 启发式是 greedy-proc，与 DP 的配对差距 −3.54。

| 规划器 | 配对差距 vs DP | vs base | CPU·s/局 |
|---|---|---|---|
| CRN rollout，8 场景 | −3.00 ± 0.47（−2.8%） | +0.54 | 0.2 |
| CRN rollout，16 场景 | −1.88 ± 0.40（−1.7%） | +1.67 | 0.5 |
| **CRN rollout，32 场景** | **−1.50 ± 0.39（−1.4%）** | **+2.04** | **1.1** |
| MCTS 200 次迭代（剪枝） | −3.63 ± 0.52（−3.3%） | −0.09 | 0.8 |
| MCTS 800 次迭代（剪枝） | −1.91 ± 0.42（−1.8%） | +1.64 | 3.0 |
| MCTS 3200 次迭代（剪枝） | −1.07 ± 0.34（−1.0%） | +2.47 | 12.9 |

怎么读这张表：
- **同等精度比算力**：rollout 16 场景（−1.88，0.5 CPU·s）对 MCTS 800 次迭代（−1.91，3.0 CPU·s），MCTS 要多花约 6 倍；
- **MCTS 能更接近最优**：3200 次迭代到 −1.07，比 rollout 32 场景（−1.50）再近约 0.4 分，代价约 12 倍算力；
- rollout 这几行对"打平时选哪个动作"很敏感，换一种打平规则会差约 0.5 分，见教训 5。

**关于规划器的五个教训**（都有实验数据支撑）：

1. **原版 UCT 在这个问题上会输给它自己的 rollout 策略**，以 greedy-proc 当 rollout 时要低 4.5–11 分，而且迭代越多不一定越好。原因是 UCT 在每个节点都要把所有动作展开一次，其中包括第 10 秒就去 PARK/CLIMB 这种一步毁掉整局的动作。这些样本被均值回传平均进所有祖先边，并且偏向不同的动作，结果把动作排序打乱了。加一条"剩余时间 > 25 s 时不考虑终局动作"之后，损失消失，迭代越多结果越好。详见 `results/tune_mcts_sweep.md`（无剪枝，扫 c）和 `results/tune_mcts_prune.md`（剪枝对照）。
2. **单局运气带来的波动远大于好动作之间的差距（1–3 分）**。由 validate 和 alliance 表的 95% CI 反推，单车 TELEOP 每局标准差约 6 分，联盟总分约 10 分。CRN rollout 让所有候选动作在同一批随机场景下比较，把大部分方差消掉了，所以达到同样精度只要 MCTS 约 1/6 的算力。这是一个在 FRC 这类问题上通用的结论：同样的算力下，配对比较的 Monte Carlo 比树搜索更划算。
3. **离散目标会遇到优化器诅咒**。在联盟实验里，rollout-win 的 P(win)：

   | 场景数 | 16 | 32 | 64 | 16，加 z=1 门控 |
   |---|---|---|---|---|
   | P(win) | 0.54 | 0.55 | 0.61 | **0.71** |

   对比：它的 base greedy-proc 是 0.63。

   原因：一个场景从输翻成赢，就能压过 20 分的得分差，于是规划器会因为某一个场景的运气偏离 base 动作。门控规则是：配对改进必须超过 1 个标准误才偏离 base。它在 16 个场景时就消除了这个问题，而且算力不增加。z=1 是事先定的，没有扫描。
4. **win 和 rp 这类离散目标需要 tie-break**。大多数决策点上，这一局在所有抽样场景里其实都已经赢定或输定了，候选动作全部打平。没有 tie-break 时，规划器会按 legal 列表顺序取第一个，也就是 L1 排在 L4 前、INTAKE 排在 CLIMB 前。修法是两处：打平时保留 base 启发式的动作；再加 1e-4/分 的期望得分作为次级排序（`policies.Objective`）。

   **消融实验**：在现在的代码上只把这两处改回去，其余不变。seed 500000 起 400 局、16 场景，结果在 `results/tie_rule_ab.md`。

   | rollout-win | P(win) | E[RP] |
   |---|---|---|
   | 修好后 | 0.52 | 3.88 |
   | 改回去 | 0.22 | 2.37 |

   对比：它的 base greedy-proc 是 P(win) 0.63。修好之后 rollout-win 仍然低于 base，这是教训 3 的优化器诅咒，要靠 z 门控解决。
5. **连续目标下也有大量精确打平，而且打平规则值约 0.5 分**（`experiments/tie_rule_ab.py`，结果在 `results/tie_rule_ab.md`）。

   **为什么会精确打平**：world 随机数按 (seed, 机器人, 动作, 第 n 次) 取。两个候选如果只是同一组动作换了顺序，比如先 INTAKE 再 REM_LOW 和反过来，它们抽到的运气是一样的。到比赛结束时它们完成的动作集合也一样，于是在所有场景里得分完全相同。

   **实测**（rollout 32 场景，30 局）：
   - 1214 个决策里有 241 个（19.9%）在最大值处精确打平，其中 232 个发生在剩余时间超过 25 s 时；
   - 其中 115 个两种规则会选不同的动作，占打平决策的 47.7%、全部决策的 9.5%。修复前的规则按 legal 顺序取第一个，所以大多是 INTAKE；现在的规则保留 base 的动作，大多是 REM_LOW、REM_HIGH 或 PROC。

   **A/B**（新 seed，配对比较；正数表示修复前的规则更好）：

   | 场景 | 目标 | 修复前 − 现在 |
   |---|---|---|
   | 单车，seed 400000–400199，16 场景 | TELEOP 分 | +0.34 ± 0.46 |
   | 单车，seed 400000–400199，32 场景 | TELEOP 分 | +0.56 ± 0.37 |
   | 联盟，seed 500000 起 400 局，16 场景 | 以 points 为目标 | 得分 +0.56 ± 0.37，P(win) +0.021 ± 0.023，E[RP] +0.005 ± 0.081 |
   | 同上 | 以 margin 为目标 | 净胜分 +0.74 ± 0.44，E[RP] +0.013 ± 0.082 |

   这里只测了 points 和 margin 两个连续目标。把上面的差值加到联盟表的这两行上，它们在 E[RP] 和 P(win) 上的名次都不变。win / rp 各行用的是同一条打平规则，没有重跑。

   **仍然保留现在的规则**，原因有两个：
   - 修复前那条规则的优势只来自 INTAKE 恰好排在动作列表第一位，没有道理可讲；
   - 现在的规则有明确性质（打平时不会比 base 差），而且联盟表里所有数字都是用它跑的。

   如果因为数字好看就换规则再重跑，等于又踩一次赢家诅咒。

   **结论**：
   - 一步前瞻在结构上看不出动作顺序的价值；
   - 打平的频率有一部分来自 CRN 的取数方式，不完全是游戏本身的性质。

   所以 rollout 离 DP 的 1.3–1.5 分差距，和一个任意 tie-break 的影响（0.3–0.6 分）是同一个量级。怎么改进列在"下一步"。

DP 最优策略在做什么（500 局平均）：
- L4 的 12 个 branch 几乎填满（平均 11.89 个），另外每局约放 1 个 L3；
- 6 个藻类全部移除，几乎全进 processor（"移藻 → 带着藻去 station 取珊瑚 → 顺路进 processor → 回 reef 放 L4"）；
- 124 s 开始去爬。

这组行为依赖两个前提：一是 `elite.hold_both=True`（能同时拿 1 珊瑚 + 1 藻类）；二是"只算自己得分"这个目标看不到 processor 送给对面 HP 的分。

## 独立审计（两轮多 agent，含对抗式复核）

带 † 的条目和数字来自审计时的一次性脚本，脚本和输出都没有进仓库。

**确认正确的部分**：
- 规则常量逐条对照手册和 TU，全部正确。
- † **DP 与单车模拟器在全尺寸下等价**：用前向概率质量传播，精确算出 DP 策略在模拟器里的值，合并后共 1,818,682 个状态。结果与 V* 相差 1.4e-10，属于浮点累积误差。
- † **另有 246 个小尺寸算例与暴力 expectimax 对拍**：覆盖多种 profile 变体和 24 个随机 profile，起始状态有 REEF、STATION、随机三类。在排队状态不起作用的设定下，最大偏差 3.6e-15。
- 规划器不会偷看：world 的 seed 和真实对手在规划时都读不到。
- † **2000 次随机配置的模糊测试**：随机化联盟组成、赛事类型和策略等，全部不变量成立。

**已修复的问题**：
- coral mark 上预置的 3 个藻类没有建模；
- playoff 仍然发 RP；
- PARK 的得分判定和 CLIMB 不一致；
- MCTS 被终局动作污染均值回传；
- 离散目标打平时按列表顺序取动作；
- reef 拥堵把已经离开 reef 的队友也计入，拥堵效应被放大约 2.6 倍 †；
- 单车会出现"幻影排队"；
- 拥堵秒数取整后，"×2"那一行实际是 2.2 倍 †；
- RolloutPolicy 无法 pickle；
- 调参和报告用了同一批 seed。

**未修，记录在案**：
- HP 投 net 没有按时间门控：终场前最后几秒才进 processor 的藻类，模型仍然算对方 HP 能投进 net。实测不影响结果 †：三种启发式各 400 局、rollout-rp（z=1）100 局，最后 5 s 内完成的 processor 都是 0 次，离终场最近的一次还剩 16 s。
- 联盟里 MCTS-rp（300 次迭代，剪枝）仍然明显落后于它的启发式：P(win) 0.23 对 0.63，E[RP] 3.27 对 4.12。原因还没定位，可能是小预算噪声、内部节点均值污染，或者 c 是在单车场景下标定的、不适用于 rp 目标。在查清之前，联盟层面请用 CRN rollout。

## 待确认的假设

1. **藻类遮挡**：手册没有写明 staged 藻类到底挡住哪些 branch。默认用解读 B（低藻挡本面 L2+L3，高藻挡本面 L3；开局 L3 可用 0 个）。解读 A 是每个藻类只挡它压着的那一对（L2/L3 各剩 6 个）。打过 2025 的队伍一看就知道哪个对，欢迎提 issue。
2. **profile 数值**：行驶矩阵、各动作耗时、成功率、HP 投 net 命中率（默认 50%）全是占位值。发现 2 的"约 68%"这个临界点直接取决于这些数。
3. **elite 能同时拿 1 珊瑚 + 1 藻类**（`hold_both=True`）。DP 最优策略里"带着藻去取珊瑚"就是靠这一条。
4. 没有防守、犯规、机构故障，也没有"掉在地上的珊瑚可以再捡"。coral mark 上的 3 个藻类默认在 TELEOP 开局时仍在地上（AUTO 对它们的影响没有建模），拾取点近似在 reef 附近。

## 下一步

1. **用 [AlphaScout](https://github.com/Alphabots-8810/AlphaScout) 标定**：TBA 的得分明细是按联盟统计的，拿不到每队的 cycle 分布，只能靠 scouting。把每队的经验分布灌进 profile，就能做赛前推演（三家怎么分工）和 picklist。
2. **2026 REBUILT**：复用引擎，只重写 game 模块。把 dumper 和 turret 当成两种 robot profile（射球时间、命中率随距离的变化、能否边走边射），用 CRN rollout 和灵敏度分析对比。
3. **加上对手与防守**：把对手从外生样本改成策略原型，算两两对阵的胜率矩阵，再用 LP 求混合均衡。
4. **规划器的打平规则**（教训 5）：让规划器能分辨"同一组动作换顺序"的差别。候选做法有两个：用"得分越早越好"的时间积分当次级 key，或对打平的候选做两步前瞻。每种都要先拿 DP 验证，再换掉现在的规则。

## 目录

```
src/frcsim/mcts.py                 与具体游戏无关的 MCTS（只按文件边界拆开，没做通用游戏接口）
src/frcsim/reefscape2025/          规则 / profile / 模拟器 / DP / 策略
experiments/                       validate、planners、tune_mcts、alliance、sensitivity、tie_rule_ab
tests/                             DP 与 expectimax 对拍（含 ring buffer 回绕）、模拟器不变量、RP 逻辑、规划器、MCTS 收敛
results/                           实验输出：validate_elite.md、alliance_{regular,champs}_B.md、sensitivity.md、tune_mcts_{prune,sweep}.md、tie_rule_ab.md
```

## License

MIT，见 [LICENSE](LICENSE)。

# 实体划分口径：边界例子（请判断）

2026-10-27。例子全部来自已评测的前 200 个 episode 的 v1 contract，引文是 prompt 原文。"现状"是 v1 contract 的做法，"建议"是我的初步判断。请在每部分末尾的问题上给出你的口径。

已定规则：穿戴、手持物品只有对情节关键时才单独列为实体；集合物算一个实体；墙不算实体，并入地点；比较明显的家具可以算实体。

**作者判断（2026-10-29）**：A1 全部单独列为实体；A2 全部单独列为实体；A3 全部并入人物描述；B 全部单独列为实体；C 全部单独列为实体。D 未提出异议，按下文理解执行。整理后的规则见 `EECBench/docs/episode-contract-v2-format.md` 的 Entity granularity 一节。下文"建议"一栏保留的是判断前的初稿，与 B、C 的结论不同处以作者判断为准。

## A. 穿戴、手持物品：什么算"对情节关键"

前 200 个 contract 里，单独列为物体的穿戴、手持物品约 250 个，其中 84 个有动作要求涉及它。

### A1. 物品本身是事件的中心（建议：单独列为实体）

| # | episode | 物品 | prompt 原文 |
| --- | --- | --- | --- |
| 1 | `5IykypzJT80_s00027` | Black pistol | "A cropped hand brings the Black pistol … in from the upper left until its muzzle rests at her right temple."（Shot2，并在 Shot4、Shot6 持续） |
| 2 | `a_jhJz5M1SQ_s00184` | Black knit cap | "He pulls the cap off and holds it beside his head"（Shot3）；"He lowers the removed Black knit cap onto the dirt beside him."（Shot4，帽子离开人物） |
| 3 | `pbmshOY3wts_s00083` | 两副墨镜 | "he grips the Black square sunglasses … and lifts them upward, revealing a separate pair of oversized Heart-shaped sunglasses already underneath"（Shot3） |
| 4 | `TTXjgOan_KI_s00013` | Long rifle | "he lifts the long rifle … brings its stock to his shoulder and settles into steady aim"（Shot2）；Shot1、Shot3 是步枪本身的特写 |
| 5 | `52apMIyJVlc_s00176` | Dark smartphone | "looks down at the dark smartphone, then raises it with his right hand to his right ear"（Shot6，打电话） |

### A2. 被拿着、有动作，但未必是情节关键（请判断）

| # | episode | 物品 | prompt 原文 |
| --- | --- | --- | --- |
| 6 | `74Od5-Fmf60_s00006`（示例 episode） | Small handheld phone | "the Small handheld phone beside his face. Across five seconds he lowers his feet, brings the phone down between his hands"（Shot2） |
| 7 | `XCAutZSdSLY_s00000` | Knife | "makes small gestures with a narrow pointed knife held raised in his hand, keeping the blade clear of the other man's body"（Shot2，Shot3、Shot4 继续拿着） |
| 8 | `5IykypzJT80_s00027` | Clear drink cup（带吸管） | "slightly raises his Clear drink cup with its pale straw and makes a small open-hand gesture"（Shot1）；Shot3 "ease it slightly lower" |
| 9 | `ChxbeG5Rq28_s00009` | Curved-handle cane | "he shifts the polished brown Curved-handle cane from near his lap to his side at screen right, then withdraws his hand"（Shot1）；Shot3 拐杖仍在身边 |
| 10 | `iBIdL_fqfio_s00044` | Dark backpack | Shot1、2、4、6 都写到抓着背包带，如 "relaxes his grip on the Dark backpack straps"（Shot4） |
| 11 | `kaZ87rTNkDA_s00010` | Stemmed glass（有红色液体） | "keeps the Stemmed glass, containing a little dark red liquid, low in her hand"（Shot2）；"holds the Stemmed glass near her chin"（Shot4） |

### A3. 只是穿着或带着，没有针对它的动作（建议：并入人物描述）

| # | episode | 物品 | prompt 原文 |
| --- | --- | --- | --- |
| 12 | `AeZQ4Oi1wu8_s00013` | Lanyard（挂工牌） | "pale badge on a dark lanyard are visible beneath his brown jacket"（Shot6）。v1 单独列为物体 |
| 13 | `dR0_tMYKwXE_s00001` | Woman's coat | "Her Beige coat is draped over her right forearm."（Shot4）。v1 单独列为物体 |
| 14 | `l1B1_jQnlFk_s00005` | Wristwatch | "He lifts his watch-wearing hand near his head"（Shot3，动作是抬手，不是针对手表）。v1 单独列为物体 |
| 15 | `74Od5-Fmf60_s00006`（示例 episode） | 项链上的徽章、眼镜 | 只出现在人物描述里。v1 没有单独列 |

**请判断**：
- A1 是否都单独列为实体？
- A2 里哪些单独列？可选的界线：（a）只有 A1 这类"物品是事件中心"的才列；（b）只要 prompt 写了针对物品本身的动作（拿起、放下、举起、挪动）就列，那么 A2 全部单独列。
- A3 是否都并入人物描述（包括 v1 已单独列出的 12–14）？

## B. 地点的结构部件（墙已定为并入地点）

| # | episode | 部件 | prompt 原文 | 现状 |
| --- | --- | --- | --- | --- |
| 16 | `74Od5-Fmf60_s00006`（示例） | Office double doors | "gray paneled double doors open onto a warmly lit hallway"（Shot1，门有开启动作）；"Keep the open door"（Shot4） | 单独实体 |
| 17 | `74Od5-Fmf60_s00006`（示例） | Office doorway、Office windows、Hallway sconce | "against the office's gray paneled doorway"；"tall gridded windows reveal city buildings"；"glowing hallway sconce" | 各自单独实体 |
| 18 | `52apMIyJVlc_s00176` | 窗户、窗框、窗栅、窗帘 | "beside the barred window"；"The dark window frame, pale patterned curtain … remain behind him"；"the white geometric grille and pale curtain remain behind him"，窗和窗帘在 4 个镜头里反复出现 | 4 个单独实体 |
| 19 | `jpTj6qTyIwY_s00011` | 管道、阀门、弯头管 | "Pale pipes with worn valves crowd the right side"；"beside a thick pale elbow pipe" | 3 个单独实体 |
| 20 | `4cSZVMEi710_s00000` | Towel ring | "a circular metal towel ring sits on the pale wall behind her" | 单独实体 |

**建议**：门、门口、窗、窗框、窗帘、管道、墙上和天花板上的固定装置，默认都并入地点描述。只有 prompt 写了针对它的动作或状态变化（如 16 的门打开）时才单独列。

**请判断**：
- 这个默认规则是否可以？
- 像 18 这样在多个镜头反复出现、作为背景标志的窗户和窗帘，是否例外、单独列？

## C. 家具与桌面小物件（明显家具可算实体）

| # | episode | 物品 | prompt 原文 | 现状 |
| --- | --- | --- | --- | --- |
| 21 | `Wl6COOA3V6Y_s00022` | Glass display counter | "stands behind a glass display counter"；"lowers her hand from the counter edge"，3 个镜头都在柜台两侧 | 单独实体 |
| 22 | `kBwF5mStXc4_s00120` | Bottle shelves、Fairy lights | "bottle shelves, hanging glassware and golden fairy lights blurred behind the worn dark partition"（酒吧背景） | 各自单独实体 |
| 23 | `4kRRDuR7OBM_s00013` | Dark desks（一组桌子）、Desk screens、Desk papers | "Staff remain at dark desks with screens and papers behind him" | 3 个集合实体 |
| 24 | `74Od5-Fmf60_s00006`（示例） | Metal drinks stand、Shaker、Lidded bucket | "a metal drinks stand holds a shaker and lidded bucket" | 3 个单独实体 |
| 25 | `Wl6COOA3V6Y_s00022` | 柜台上的小物件 | "Papers and a pencil lie before her, with a panda-shaped holder and pale cup nearby and an electronic scale to the right" | Pale cup 等各自单独实体 |
| 26 | `tIB4z4uMeNs_s00023` | Green glass lamp、桌面文件 | "a green glass lamp and silver accessories stand among papers on the desktop" | 各自单独实体 |

**建议**：
- 人物使用或接触的家具（21 的柜台）、前景中的主要家具（示例里的桌子、椅子）列为实体。
- 只作为背景陈设一笔带过的（22 的酒架）并入地点描述。
- 家具上的小物件（24 的 shaker 和 bucket、25、26）默认并入所在家具的描述；有人拿起、使用时，按 A 部分的规则处理。

**请判断**：
- "明显"的标准是否按"有人使用或接触、或位于前景"？
- 桌面小物件是否默认并入家具描述？

## D. 集合物（已定：一个集合算一个实体）

我的理解如下，不同意的话请指出：
- prompt 作为一个整体描述的一群，算一个实体，例如 "colorful dancing guests"、"loose papers"、"city buildings"、"pale pipes"、"dark desks"。人群也一样，算一个人物实体。
- prompt 把同类东西分开描述时，各算一个实体，例如前后两只杯子分别描述（"the separate rear green mug"），或 3 号的两副墨镜。

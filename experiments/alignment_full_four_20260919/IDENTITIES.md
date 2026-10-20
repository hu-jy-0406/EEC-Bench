# 最新四组实验：实体清单与跨shot身份对应

本表来自最终matching.json与identity_review.json，不是初始anchor匹配。Shot1/Shot3同场景做身份对应；Shot2为独立走廊场景，仅检测聚类，不进行跨场景身份连接。未匹配不等于存在性冲突；可因视角、运动、证据不足或不同实例。

四组每shot均21/7/22个局部实体。Study2两方法确认9对(8静止+1运动女子)；Study3两方法确认10对(9静止+1运动女子)。两方法的已确认匹配集合逐ID比较一致。Study3多出黑色/白色台灯对应。

女子：Study2 shot1/e4↔shot3/e22，Study3 shot1/e4↔shot3/e21；四组均g04、matched、两侧moving，复核action=keep。复核依据包括灰色毛衣/深色裤子/发髻等视觉信息及拿书离开、空手返回的正常叙事和逐帧动作证据；未要求跨时刻三维中心重合。红色硬皮书为Shot1运动实体，Shot3无对应；Shot2也检测到红书，但不跨场景匹配。

## study2_fps32

|组ID|最终身份状态|Shot1实体|Shot3实体|运动状态|
|---|---|---|---|---|
|g01_a|unmatched|shot1/e1 Framed landscape painting|—|static|
|g01_b|unmatched|—|shot3/e1 Framed landscape painting|static|
|g02|matched|shot1/e2 Dark green mug|shot3/e2 Dark green mug|static / static|
|g03|unmatched|shot1/e3 Black desk lamp|—|static|
|g04|matched|shot1/e4 Woman in a gray sweater and dark trousers|shot3/e22 Woman wearing a gray sweater and dark trousers|moving / moving|
|g05|matched|shot1/e5 Large wooden desk|shot3/e7 Large wooden dining table|static / static|
|g06|unmatched|shot1/e6 Small framed picture on bookshelf|—|static|
|g07|matched|shot1/e7 Pencil cup|shot3/e9 Pencil cup|static / static|
|g08|unmatched|shot1/e8 Books on lower bookshelf shelf|—|static|
|g09|matched|shot1/e9 Trailing plant by window|shot3/e10 Trailing plant by the window|static / static|
|g10|unmatched|shot1/e10 Dark bookcase|—|static|
|g11|ambiguous|shot1/e11 Trailing plant on bookshelf|shot3/e13 Plant at the far left edge|static / static|
|g12|matched|shot1/e12 Patterned rug|shot3/e15 Patterned rug beneath the dining table|static / static|
|g13|unmatched|shot1/e13 Red hardcover book|—|moving|
|g14|matched|shot1/e14 Wooden chair|shot3/e6 Wooden chair|static / static|
|g15|matched|shot1/e15 Radiator beneath window|shot3/e18 Radiator|static / static|
|g16|unmatched|shot1/e16 Books on upper bookshelf shelf|—|static|
|g17|matched|shot1/e17 Plant pot by window|shot3/e17 Plant pot by the window|static / static|
|g18|unmatched|shot1/e18 Small ceramic pot on bookshelf|—|static|
|g19|scope_mismatch|shot1/e19 Black pen in pencil cup|shot3/e19 Writing implements in the pencil cup|static / static|
|g20_a|unmatched|shot1/e20 Small wooden side table|—|static|
|g20_b|unmatched|—|shot3/e8 Wooden console table|static|
|g21_a|unmatched|shot1/e21 Plant on side table|—|static|
|g21_b|unmatched|—|shot3/e11 Trailing plant on the console table|static|
|g22|unmatched|—|shot3/e3 Framed picture on the left hallway wall|static|
|g23|unmatched|—|shot3/e4 Framed botanical picture|static|
|g24|unmatched|—|shot3/e5 Small framed picture beside the doorway|static|
|g25|unmatched|—|shot3/e12 Small wooden cabinet in the hallway|static|
|g26|unmatched|—|shot3/e14 Tissue packet with protruding tissue|static|
|g27|unmatched|—|shot3/e16 Stack of books on the console table|static|
|g28|unmatched|—|shot3/e20 Hallway rug|static|
|g29|unmatched|—|shot3/e21 Plant pot on the console table|static|

### 人物复核原文

{
  "initial_group_id": "g04",
  "action": "keep",
  "result_group_ids": [
    "g04"
  ],
  "geometry_interpretation": "0.78的代表中心差不是固定占位差；逐帧轨迹记录离开和返回。",
  "visual_identity_evidence": "面部、棕色松髻、灰褐毛衣和深裤对应。",
  "same_instance_motion_alternative": "p01、p02、p06、p10明确支持同一女子拿本离开、空手返回；两侧moving不变。",
  "witnesses": [
    {
      "shot_id": "shot1",
      "frame_id": 0,
      "region_xyxy": [
        190,
        2,
        469,
        309
      ],
      "observation": "坐姿面貌、发髻和衣着。"
    },
    {
      "shot_id": "shot1",
      "frame_id": 72,
      "region_xyxy": [
        45,
        0,
        406,
        480
      ],
      "observation": "起身持红本离开。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 24,
      "region_xyxy": [
        106,
        12,
        199,
        238
      ],
      "observation": "同衣着女子从门口空手进入。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 120,
      "region_xyxy": [
        462,
        0,
        631,
        319
      ],
      "observation": "面貌和发髻对应，空手停在椅旁。"
    }
  ]
}

### 逐shot检测聚类清单

**shot1：21个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Black desk lamp
- e4：Woman in a gray sweater and dark trousers
- e5：Large wooden desk
- e6：Small framed picture on bookshelf
- e7：Pencil cup
- e8：Books on lower bookshelf shelf
- e9：Trailing plant by window
- e10：Dark bookcase
- e11：Trailing plant on bookshelf
- e12：Patterned rug
- e13：Red hardcover book
- e14：Wooden chair
- e15：Radiator beneath window
- e16：Books on upper bookshelf shelf
- e17：Plant pot by window
- e18：Small ceramic pot on bookshelf
- e19：Black pen in pencil cup
- e20：Small wooden side table
- e21：Plant on side table

**shot2：7个**

- e1：Woman wearing a gray sweater and black trousers
- e2：Right framed botanical print
- e3：Left framed botanical print
- e4：Wooden console table
- e5：Red hardcover book
- e6：Patterned hallway runner rug
- e7：Door strike plate

**shot3：22个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Framed picture on the left hallway wall
- e4：Framed botanical picture
- e5：Small framed picture beside the doorway
- e6：Wooden chair
- e7：Large wooden dining table
- e8：Wooden console table
- e9：Pencil cup
- e10：Trailing plant by the window
- e11：Trailing plant on the console table
- e12：Small wooden cabinet in the hallway
- e13：Plant at the far left edge
- e14：Tissue packet with protruding tissue
- e15：Patterned rug beneath the dining table
- e16：Stack of books on the console table
- e17：Plant pot by the window
- e18：Radiator
- e19：Writing implements in the pencil cup
- e20：Hallway rug
- e21：Plant pot on the console table
- e22：Woman wearing a gray sweater and dark trousers


## study2_codex_direct

|组ID|最终身份状态|Shot1实体|Shot3实体|运动状态|
|---|---|---|---|---|
|g01_a|unmatched|shot1/e1 Framed landscape painting|—|static|
|g01_b|unmatched|—|shot3/e1 Framed landscape painting|static|
|g02|matched|shot1/e2 Dark green mug|shot3/e2 Dark green mug|static / static|
|g03|unmatched|shot1/e3 Black desk lamp|—|static|
|g04|matched|shot1/e4 Woman wearing a gray sweater and dark trousers|shot3/e22 Woman wearing a gray sweater and dark trousers|moving / moving|
|g05|matched|shot1/e5 Large wooden desk|shot3/e7 Wooden dining table|static / static|
|g06|unmatched|shot1/e6 Small framed picture on bookshelf|—|static|
|g07|matched|shot1/e7 Pencil cup|shot3/e9 White pencil cup|static / static|
|g08|unmatched|shot1/e8 Collection of books on lower shelf|—|static|
|g09|matched|shot1/e9 Trailing plant by window|shot3/e10 Trailing plant by the window|static / static|
|g10|unmatched|shot1/e10 Dark bookcase|—|static|
|g11|ambiguous|shot1/e11 Trailing plant on bookshelf|shot3/e13 Plant at the left edge|static / static|
|g12|matched|shot1/e12 Patterned rug beneath desk|shot3/e15 Patterned rug beneath the dining table|static / static|
|g13|unmatched|shot1/e13 Red hardcover book carried by woman|—|moving|
|g14|matched|shot1/e14 Wooden chair|shot3/e6 Wooden dining chair|static / static|
|g15|matched|shot1/e15 Radiator beneath window|shot3/e18 Radiator|static / static|
|g16|unmatched|shot1/e16 Collection of books on top shelf|—|static|
|g17|matched|shot1/e17 Plant pot by window|shot3/e17 Plant pot on the windowsill|static / static|
|g18|unmatched|shot1/e18 Small ceramic pot on bookshelf|—|static|
|g19|scope_mismatch|shot1/e19 Black pen in pencil cup|shot3/e19 Writing utensils in the pencil cup|static / static|
|g20_a|unmatched|shot1/e20 Small wooden side table|—|static|
|g20_b|unmatched|—|shot3/e8 Wooden console table|static|
|g21_a|unmatched|shot1/e21 Plant on side table|—|static|
|g21_b|unmatched|—|shot3/e11 Trailing plant on the console table|static|
|g22|unmatched|—|shot3/e3 Larger framed hallway picture|static|
|g23|unmatched|—|shot3/e4 Framed botanical picture|static|
|g24|unmatched|—|shot3/e5 Smaller framed hallway picture|static|
|g25|unmatched|—|shot3/e12 Small wooden hallway cabinet|static|
|g26|unmatched|—|shot3/e14 Tissue packet with protruding tissue|static|
|g27|unmatched|—|shot3/e16 Stack of books on the console table|static|
|g28|unmatched|—|shot3/e20 Hallway rug|static|
|g29|unmatched|—|shot3/e21 Plant pot on the console table|static|

### 人物复核原文

{
  "initial_group_id": "g04",
  "action": "keep",
  "result_group_ids": [
    "g04"
  ],
  "geometry_interpretation": "两侧代表框来自不同动作时刻，距离0.65不是固定占位差。",
  "visual_identity_evidence": "脸形、棕色松髻、灰褐毛衣与深裤一致。",
  "same_instance_motion_alternative": "p01、p02、p06、p10明确同一女子拿书离开并空手返回，逐帧轨迹支持。",
  "witnesses": [
    {
      "shot_id": "shot1",
      "frame_id": 0,
      "region_xyxy": [
        190,
        2,
        469,
        309
      ],
      "observation": "坐在原椅上的女子。"
    },
    {
      "shot_id": "shot1",
      "frame_id": 72,
      "region_xyxy": [
        45,
        0,
        406,
        480
      ],
      "observation": "持红本起身。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 24,
      "region_xyxy": [
        106,
        12,
        199,
        238
      ],
      "observation": "空手进门。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 120,
      "region_xyxy": [
        462,
        0,
        631,
        319
      ],
      "observation": "同一女子停在椅旁。"
    }
  ]
}

### 逐shot检测聚类清单

**shot1：21个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Black desk lamp
- e4：Woman wearing a gray sweater and dark trousers
- e5：Large wooden desk
- e6：Small framed picture on bookshelf
- e7：Pencil cup
- e8：Collection of books on lower shelf
- e9：Trailing plant by window
- e10：Dark bookcase
- e11：Trailing plant on bookshelf
- e12：Patterned rug beneath desk
- e13：Red hardcover book carried by woman
- e14：Wooden chair
- e15：Radiator beneath window
- e16：Collection of books on top shelf
- e17：Plant pot by window
- e18：Small ceramic pot on bookshelf
- e19：Black pen in pencil cup
- e20：Small wooden side table
- e21：Plant on side table

**shot2：7个**

- e1：Woman wearing a gray sweater and black trousers
- e2：Right framed botanical print
- e3：Left framed botanical print
- e4：Wooden console table
- e5：Red hardcover book
- e6：Patterned hallway runner rug
- e7：Door hinge on the left doorway

**shot3：22个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Larger framed hallway picture
- e4：Framed botanical picture
- e5：Smaller framed hallway picture
- e6：Wooden dining chair
- e7：Wooden dining table
- e8：Wooden console table
- e9：White pencil cup
- e10：Trailing plant by the window
- e11：Trailing plant on the console table
- e12：Small wooden hallway cabinet
- e13：Plant at the left edge
- e14：Tissue packet with protruding tissue
- e15：Patterned rug beneath the dining table
- e16：Stack of books on the console table
- e17：Plant pot on the windowsill
- e18：Radiator
- e19：Writing utensils in the pencil cup
- e20：Hallway rug
- e21：Plant pot on the console table
- e22：Woman wearing a gray sweater and dark trousers


## study3_fps32

|组ID|最终身份状态|Shot1实体|Shot3实体|运动状态|
|---|---|---|---|---|
|g01_a|unmatched|shot1/e1 Framed landscape painting|—|static|
|g01_b|unmatched|—|shot3/e1 Framed landscape painting|static|
|g02|matched|shot1/e2 Dark green mug|shot3/e2 Dark green mug|static / static|
|g03|matched|shot1/e3 Black desk lamp|shot3/e4 White desk lamp|static / static|
|g04|matched|shot1/e4 Woman in a gray sweater|shot3/e21 Woman wearing gray sweater and dark trousers|moving / moving|
|g05|matched|shot1/e5 Large wooden desk|shot3/e7 Large wooden table|static / static|
|g06|unmatched|shot1/e6 Small framed photograph|—|static|
|g07|matched|shot1/e7 Pencil holder|shot3/e10 Pencil cup|static / static|
|g08|unmatched|shot1/e8 Books on the lower bookshelf shelf|—|static|
|g09|matched|shot1/e9 Trailing plant beside the window|shot3/e12 Trailing plant on windowsill|static / static|
|g10|unmatched|shot1/e10 Dark bookcase|—|static|
|g11|unmatched|shot1/e11 Trailing plant on the bookcase|—|static|
|g12|matched|shot1/e12 Patterned rug|shot3/e16 Large patterned rug beneath table|static / static|
|g13|unmatched|shot1/e13 Red hardcover book|—|moving|
|g14|matched|shot1/e14 Wooden chair|shot3/e6 Wooden chair|static / static|
|g15|matched|shot1/e15 Radiator beneath the window|shot3/e15 Radiator|static / static|
|g16|unmatched|shot1/e16 Books on the upper bookshelf shelf|—|static|
|g17|matched|shot1/e17 Terracotta plant pot beside the window|shot3/e14 Windowsill plant pot|static / static|
|g18|unmatched|shot1/e18 Small light-colored pot on the bookcase|—|static|
|g19|scope_mismatch|shot1/e19 Black pen in the pencil holder|shot3/e17 Writing utensils in pencil cup|static / static|
|g20_a|unmatched|shot1/e20 Small wooden side table|—|static|
|g20_b|unmatched|—|shot3/e9 Wooden console table|static|
|g21_a|unmatched|shot1/e21 Plant on the side table|—|static|
|g21_b|unmatched|—|shot3/e11 Trailing plant on console table|static|
|g22|unmatched|—|shot3/e3 Larger framed hallway picture|static|
|g23|unmatched|—|shot3/e5 Framed botanical picture|static|
|g24|unmatched|—|shot3/e8 Smaller framed hallway picture|static|
|g25|unmatched|—|shot3/e13 Tissue packet|static|
|g26|unmatched|—|shot3/e18 Console table plant pot|static|
|g27|unmatched|—|shot3/e19 Stack of books|static|
|g28|unmatched|—|shot3/e20 Hallway rug|static|
|g29|unmatched|—|shot3/e22 Small hallway cabinet|static|

### 人物复核原文

{
  "initial_group_id": "g04",
  "action": "keep",
  "result_group_ids": [
    "g04"
  ],
  "geometry_interpretation": "2.631代表框间距是不同时间的运动位置，不能作为固定占位冲突。",
  "visual_identity_evidence": "脸部、发髻与服装一致，连续动作与p01、p10对应。",
  "same_instance_motion_alternative": "p02–p06明确离开、走廊放本后返回；逐帧轨迹支持同一人物移动。",
  "witnesses": [
    {
      "shot_id": "shot1",
      "frame_id": 0,
      "region_xyxy": [
        190,
        2,
        469,
        309
      ],
      "observation": "坐着的女子面部与服装。"
    },
    {
      "shot_id": "shot1",
      "frame_id": 72,
      "region_xyxy": [
        45,
        0,
        406,
        480
      ],
      "observation": "拿红本起身离开。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 24,
      "region_xyxy": [
        45,
        13,
        148,
        300
      ],
      "observation": "同装束女子从门口空手进入。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 120,
      "region_xyxy": [
        467,
        0,
        638,
        319
      ],
      "observation": "同面部和发髻，双手空着站在椅旁。"
    }
  ]
}

### 逐shot检测聚类清单

**shot1：21个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Black desk lamp
- e4：Woman in a gray sweater
- e5：Large wooden desk
- e6：Small framed photograph
- e7：Pencil holder
- e8：Books on the lower bookshelf shelf
- e9：Trailing plant beside the window
- e10：Dark bookcase
- e11：Trailing plant on the bookcase
- e12：Patterned rug
- e13：Red hardcover book
- e14：Wooden chair
- e15：Radiator beneath the window
- e16：Books on the upper bookshelf shelf
- e17：Terracotta plant pot beside the window
- e18：Small light-colored pot on the bookcase
- e19：Black pen in the pencil holder
- e20：Small wooden side table
- e21：Plant on the side table

**shot2：7个**

- e1：Woman wearing a gray sweater and black trousers
- e2：Right framed botanical print
- e3：Left framed botanical print
- e4：Wooden console table
- e5：Red hardcover book
- e6：Patterned hallway runner rug
- e7：Door strike plate

**shot3：22个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Larger framed hallway picture
- e4：White desk lamp
- e5：Framed botanical picture
- e6：Wooden chair
- e7：Large wooden table
- e8：Smaller framed hallway picture
- e9：Wooden console table
- e10：Pencil cup
- e11：Trailing plant on console table
- e12：Trailing plant on windowsill
- e13：Tissue packet
- e14：Windowsill plant pot
- e15：Radiator
- e16：Large patterned rug beneath table
- e17：Writing utensils in pencil cup
- e18：Console table plant pot
- e19：Stack of books
- e20：Hallway rug
- e21：Woman wearing gray sweater and dark trousers
- e22：Small hallway cabinet


## study3_codex_direct

|组ID|最终身份状态|Shot1实体|Shot3实体|运动状态|
|---|---|---|---|---|
|g01_a|unmatched|shot1/e1 Framed landscape painting|—|static|
|g01_b|unmatched|—|shot3/e1 Framed landscape painting|static|
|g02|matched|shot1/e2 Dark green mug|shot3/e2 Dark green mug|static / static|
|g03|matched|shot1/e3 Desk lamp|shot3/e4 White desk lamp|static / static|
|g04|matched|shot1/e4 Woman wearing a gray sweater and dark trousers|shot3/e21 Woman in gray sweater and dark trousers|moving / moving|
|g05|matched|shot1/e5 Large wooden desk|shot3/e7 Large wooden table|static / static|
|g06|unmatched|shot1/e6 Small framed picture on bookshelf|—|static|
|g07|matched|shot1/e7 Pencil holder|shot3/e10 Pencil holder|static / static|
|g08|unmatched|shot1/e8 Collection of books on lower shelf|—|static|
|g09|matched|shot1/e9 Trailing plant by window|shot3/e12 Trailing plant on windowsill|static / static|
|g10|unmatched|shot1/e10 Dark bookcase|—|static|
|g11|unmatched|shot1/e11 Trailing plant on bookshelf|—|static|
|g12|matched|shot1/e12 Patterned rug|shot3/e16 Patterned rug beneath table|static / static|
|g13|unmatched|shot1/e13 Red hardcover book|—|moving|
|g14|matched|shot1/e14 Wooden chair|shot3/e6 Wooden chair|static / static|
|g15|matched|shot1/e15 Radiator|shot3/e15 Radiator|static / static|
|g16|unmatched|shot1/e16 Collection of books on top shelf|—|static|
|g17|matched|shot1/e17 Terracotta plant pot by window|shot3/e14 Windowsill plant pot|static / static|
|g18|unmatched|shot1/e18 Small pot on bookshelf|—|static|
|g19|scope_mismatch|shot1/e19 Black pen in pencil holder|shot3/e17 Writing utensils in holder|static / static|
|g20_a|unmatched|shot1/e20 Small wooden side table|—|static|
|g20_b|unmatched|—|shot3/e9 Wooden console table|static|
|g21|ambiguous|shot1/e21 Plant on side table|shot3/e11 Trailing plant on console table|static / static|
|g22|unmatched|—|shot3/e3 Larger framed hallway picture|static|
|g23|unmatched|—|shot3/e5 Framed botanical picture|static|
|g24|unmatched|—|shot3/e8 Smaller framed hallway picture|static|
|g25|unmatched|—|shot3/e13 Tissue packet|static|
|g26|unmatched|—|shot3/e18 Console table plant pot|static|
|g27|unmatched|—|shot3/e19 Stack of books|static|
|g28|unmatched|—|shot3/e20 Hallway rug|static|
|g29|unmatched|—|shot3/e22 Small hallway cabinet|static|

### 人物复核原文

{
  "initial_group_id": "g04",
  "action": "keep",
  "result_group_ids": [
    "g04"
  ],
  "geometry_interpretation": "3.08的代表框差来自不同时刻；shot3逐帧轨迹从门口走向椅旁，不能按固定占位判断。",
  "visual_identity_evidence": "同一面容、棕发松髻、灰褐毛衣和深裤。",
  "same_instance_motion_alternative": "p01、p02、p05、p06、p10直接支持同人离开后空手返回。",
  "witnesses": [
    {
      "shot_id": "shot1",
      "frame_id": 0,
      "region_xyxy": [
        190,
        2,
        469,
        309
      ],
      "observation": "坐着的女子面容和服装。"
    },
    {
      "shot_id": "shot1",
      "frame_id": 72,
      "region_xyxy": [
        45,
        0,
        406,
        480
      ],
      "observation": "起身手持红本。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 24,
      "region_xyxy": [
        45,
        13,
        148,
        300
      ],
      "observation": "同服装女子空手进门。"
    },
    {
      "shot_id": "shot3",
      "frame_id": 120,
      "region_xyxy": [
        467,
        0,
        638,
        319
      ],
      "observation": "同面容及松髻，双手空着站在椅旁。"
    }
  ]
}

### 逐shot检测聚类清单

**shot1：21个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Desk lamp
- e4：Woman wearing a gray sweater and dark trousers
- e5：Large wooden desk
- e6：Small framed picture on bookshelf
- e7：Pencil holder
- e8：Collection of books on lower shelf
- e9：Trailing plant by window
- e10：Dark bookcase
- e11：Trailing plant on bookshelf
- e12：Patterned rug
- e13：Red hardcover book
- e14：Wooden chair
- e15：Radiator
- e16：Collection of books on top shelf
- e17：Terracotta plant pot by window
- e18：Small pot on bookshelf
- e19：Black pen in pencil holder
- e20：Small wooden side table
- e21：Plant on side table

**shot2：7个**

- e1：Woman wearing a gray sweater and dark trousers
- e2：Larger framed botanical print on the right
- e3：Smaller framed botanical print on the left
- e4：Wooden console table
- e5：Red hardcover book
- e6：Patterned hallway runner rug
- e7：Door hinge on the left doorway

**shot3：22个**

- e1：Framed landscape painting
- e2：Dark green mug
- e3：Larger framed hallway picture
- e4：White desk lamp
- e5：Framed botanical picture
- e6：Wooden chair
- e7：Large wooden table
- e8：Smaller framed hallway picture
- e9：Wooden console table
- e10：Pencil holder
- e11：Trailing plant on console table
- e12：Trailing plant on windowsill
- e13：Tissue packet
- e14：Windowsill plant pot
- e15：Radiator
- e16：Patterned rug beneath table
- e17：Writing utensils in holder
- e18：Console table plant pot
- e19：Stack of books
- e20：Hallway rug
- e21：Woman in gray sweater and dark trousers
- e22：Small hallway cabinet


## 未确定对应与方法差异

- Study2两方案最终对应关系逐ID相同。书架垂吊植物↔Shot3左边缘植物为ambiguous。
- Study3的边桌植物：FPS32拆为两个未匹配实体，Codex直接方案保留ambiguous；不影响10对confirmed matched集合。
- 两测例均将单支黑笔↔一组书写工具标scope_mismatch，未强行一对一。
- 挂画、边桌等初始对应在复核后被拆开，不应把它们列作已确认共现实体。
- 本报告核对输出与视觉证据记录，不提供全部实体匹配准确率的人工真值标注。

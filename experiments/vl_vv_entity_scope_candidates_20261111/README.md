# Candidate entity categories that would add unspecified entities (2026-11-11)

Times are Dubai time. Analysis only: zero model calls, nothing live changed, no commit.

## Owner request

2026-11-11: "我之后要继续增加这个比例，下一步修改实体定义，把穿戴物等容易出现unspecified情形但之前没算做实体的考虑进来。
请先给我根据之前的运行经验列一个这种增量实体类别的清单我看看。"

## Sources

- C full run (`../vl_vv_full_first200_c_20261110`, 1,000 videos, 5,000 shots, fresh shot clustering):
  - `absorbed_labels.py` -> `absorbed_labels.json`: WeDetect candidates absorbed into another entity (a candidate
    inside an entity whose most frequent label differs), candidates the clustering agent rejected, with reasons.
  - `floor_and_place_labels.py`: floor coverings removed before clustering (533 detections, 113 shots, 43 videos)
    and WeDetect labels for walls/floors/ceilings (rare: 地板/地面 115 detections in 16 videos).
  - `issue_categories.py`, `issue_subcategories.py`, `subject_kinds.py`: confirmed V-V issues of C + plug-in by
    subcategory, subject kind and items named in character-appearance descriptions (keyword matching, multi-label,
    approximate: entity names such as "深色夹克访客" and face-identity descriptions also match).
- Worn-item pilot (`../vl_vv_worn_entities_pilot_20261109`, 40 videos): worn items as entities raised the share of
  confirmed V-V issues with an unspecified subject from 0/122 to 28/111 (21 with a worn-item subject), mostly by
  moving issues from the wearer to the item; 19 of the 28 concern items the prompt names.
- Wall audit (`../vl_vv_full_first200_v3_20261109/README.md`): before the 2026-11-09 wall rule, 21 of 42 issues
  counted unspecified had an agent-added wall/floor/ground subject.

## Key numbers (C + plug-in, confirmed V-V issues: 3,213; 263 with an unspecified subject)

- Subject kinds: character 1,673, object 603, no subject 490, unspecified-only 218, location-only 107 (64 setting
  background, 36 lighting), mixed 124.
- Character appearance (cross 931, within 87) issues naming: clothing 534, hair/beard 384, headwear 101, tie/scarf
  76, eyewear 73, jewelry/watch 47, trousers 39, belt/badge/lanyard 36, gloves/apron 13, footwear 3, bag 2.

## Which categories would add unspecified issues (owner question 2026-11-11)

Owner: "我有点担心有的类别增加后，只会增加specified审核压力，不会增加unspecified数量". An item becomes an unspecified
entity only when the prompt does not name it; a named item would become a specified contract entity.

- `category_yield.py` -> `category_yield.json` (category level): episodes naming the category (of 200): clothing 195,
  wall/floor/ceiling 121, trousers/skirt 92, jewelry/watch 85 (inflated by "watch"/"ring" as verbs), trees/plants
  72, headwear 58, belt/badge 52, tie/scarf 50, eyewear 45, ground 43, footwear 31, gloves/apron 17, bag 15, floor
  covering 11.
- `item_named.py` -> `item_named.json` (issue level, approximate keyword mapping of the issue's Chinese item word to
  English prompt words): of 882 confirmed specified-subject issues naming a candidate item, the item is not named in
  the subject's own contract name/description in 341 and nowhere in the prompt in 157. Per category (issues / named
  for the subject / not named for the subject): clothing 494 / 349 / 145, wall-floor-ceiling 145 / 73 / 72, headwear
  108 / 77 / 31, eyewear 81 / 54 / 27, tie-scarf 84 / 60 / 24, belt-badge 37 / 13 / 24, ground 31 / 10 / 21,
  trousers 46 / 32 / 14, trees 25 / 12 / 13, jewelry 50 / 44 / 6, gloves 12 / 10 / 2, footwear 3 / 3 / 0, bag 2 / 2 / 0.
- Upper bounds if every issue whose item is not named for its subject moved to an unspecified item (current
  263 / 3,213 = 8.19%): all categories +341 (18.8%), worn items +242 (15.7%), clothing only +145 (12.7%), set without
  clothing/jewelry/footwear/bag/gloves +211 (14.8%), place parts +100 (11.3%). Relabeling only; new detections not
  estimated (the 2026-11-09 pilot found almost none).

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

# Contract v2 draft: 74Od5-Fmf60_s00006_n4_clean_v2

Model-facing version (no evidence). Converted from the v1 contract; 161 v1 claims: 40 → presence, 60 → entity_description, 20 → motion, 39 → spatial, 1 → appearance, 1 → shot_description.camera_view.

## entity_descriptions

| id | label | name | description |
|---|---|---|---|
| 0 | character | Dark-jacket visitor | Short man with dark hair, wearing a black leather jacket over a dark hooded layer and a striped gray shirt, with a gold-colored badge on a neck chain. |
| 1 | character | Beige-jacket visitor | Man taller than the Dark-jacket visitor, wearing thin metal-framed glasses, a beige jacket and a pale collared shirt. |
| 2 | character | Doorway woman | Blonde woman with pinned-up hair, wearing a dark sleeveless dress. |
| 3 | character | Suited man | Man with wavy brown hair, wearing a dark suit, a pale pink striped shirt, a red tie with a matching pocket square, and black shoes. |
| 4 | location | Hallway | Warmly lit hallway outside the office. |
| 5 | location | Office | Office with pale paneled walls, a desk and city-facing windows. |
| 6 | object | Office double doors | Gray paneled double doors between the office and the hallway. |
| 7 | object | Office framed art | Framed abstract art on the office wall. |
| 8 | object | Black chair | Black chair. |
| 9 | object | Wooden office desk | Wooden office desk. |
| 10 | object | Small handheld phone | Small handheld phone. |
| 11 | object | Open black laptop | Black laptop. |
| 12 | object | Dark writing mat | Dark writing mat. |
| 13 | object | Loose papers | Loose sheets of paper. |
| 14 | object | Office windows | Tall gridded office windows. |
| 15 | object | City buildings | City buildings outside the office windows. |
| 16 | object | Metal drinks stand | Metal drinks stand. |
| 17 | object | Shaker | Shaker. |
| 18 | object | Lidded bucket | Bucket with a lid. |
| 19 | object | Office doorway | Gray paneled doorway of the office. |
| 20 | object | Hallway sconce | Glowing hallway sconce. |
| 21 | object | Framed black line portrait | Framed portrait drawn in black lines. |

## Shot1

- **locations**: 5 Office
- **camera_view**: Medium view.
- **camera_movement**: The camera follows the men leftward as they enter, revealing framed art along the office wall.
- **transition_from_previous**: None
- **presence**: 0 Dark-jacket visitor, 1 Beige-jacket visitor, 2 Doorway woman, 4 Hallway, 5 Office, 6 Office double doors, 7 Office framed art

**appearance** (0)

(none)

**spatial** (4)

| id | entities | expected | quantifier |
|---|---|---|---|
| S1-spa-1 | 6 Office double doors, 4 Hallway | The doors open onto the hallway. | exists |
| S1-spa-2 | 2 Doorway woman, 0 Dark-jacket visitor, 1 Beige-jacket visitor | The woman is visible behind the two visitors. | exists |
| S1-spa-3 | 0 Dark-jacket visitor, 1 Beige-jacket visitor | The Dark-jacket visitor is in front of the Beige-jacket visitor during their entrance. | when_visible |
| S1-spa-4 | 7 Office framed art, 5 Office | The framed art is along the office wall. | when_visible |

**motion** (4)

| id | entities | expected | quantifier |
|---|---|---|---|
| S1-mot-1 | 6 Office double doors | The double doors open. | exists |
| S1-mot-2 | 0 Dark-jacket visitor, 5 Office | The Dark-jacket visitor walks into the office. | exists |
| S1-mot-3 | 1 Beige-jacket visitor, 0 Dark-jacket visitor, 5 Office | The Beige-jacket visitor follows the Dark-jacket visitor into the office. | exists |
| S1-mot-4 | 0 Dark-jacket visitor, 1 Beige-jacket visitor | The men move leftward as they enter. | exists |

## Shot2

- **locations**: 5 Office
- **camera_view**: None
- **camera_movement**: None
- **transition_from_previous**: cut
- **presence**: 3 Suited man, 5 Office, 8 Black chair, 9 Wooden office desk, 10 Small handheld phone, 11 Open black laptop, 12 Dark writing mat, 13 Loose papers, 14 Office windows, 15 City buildings, 16 Metal drinks stand, 17 Shaker, 18 Lidded bucket

**appearance** (1)

| id | entities | expected | quantifier |
|---|---|---|---|
| S2-app-1 | 5 Office | The office is lit by daylight. | when_visible |

**spatial** (12)

| id | entities | expected | quantifier |
|---|---|---|---|
| S2-spa-1 | 3 Suited man, 8 Black chair | The man initially reclines in the chair. | start |
| S2-spa-2 | 3 Suited man, 8 Black chair, 9 Wooden office desk | The man and his chair are behind the desk. | start |
| S2-spa-3 | 3 Suited man, 9 Wooden office desk | Both of his shoes are initially on the desktop. | start |
| S2-spa-4 | 10 Small handheld phone, 3 Suited man | The phone is initially beside the man's face. | start |
| S2-spa-5 | 11 Open black laptop | The laptop is open. | when_visible |
| S2-spa-6 | 11 Open black laptop, 12 Dark writing mat | The laptop is on the writing mat. | when_visible |
| S2-spa-7 | 13 Loose papers, 11 Open black laptop, 12 Dark writing mat | The loose papers are near the laptop and writing mat. | when_visible |
| S2-spa-8 | 14 Office windows, 3 Suited man | The windows are behind the Suited man. | when_visible |
| S2-spa-9 | 15 City buildings, 14 Office windows | City buildings are visible through the windows. | exists |
| S2-spa-10 | 16 Metal drinks stand, 3 Suited man | The drinks stand is behind the Suited man. | when_visible |
| S2-spa-11 | 16 Metal drinks stand, 17 Shaker | The drinks stand holds the shaker. | when_visible |
| S2-spa-12 | 16 Metal drinks stand, 18 Lidded bucket | The drinks stand holds the bucket. | when_visible |

**motion** (4)

| id | entities | expected | quantifier |
|---|---|---|---|
| S2-mot-1 | 3 Suited man | He lowers his feet. | exists |
| S2-mot-2 | 3 Suited man, 10 Small handheld phone | He brings the phone down between his hands. | exists |
| S2-mot-3 | 3 Suited man | He leans forward. | exists |
| S2-mot-4 | 3 Suited man | He begins to stand; completed standing is not required in this shot. | exists |

## Shot3

- **locations**: 5 Office
- **camera_view**: A wider view across the Wooden office desk.
- **camera_movement**: A gentle leftward reframing reveals the Suited man standing behind the desk.
- **transition_from_previous**: cut
- **presence**: 0 Dark-jacket visitor, 1 Beige-jacket visitor, 3 Suited man, 5 Office, 7 Office framed art, 9 Wooden office desk, 11 Open black laptop, 14 Office windows, 16 Metal drinks stand

**appearance** (0)

(none)

**spatial** (12)

| id | entities | expected | quantifier |
|---|---|---|---|
| S3-spa-1 | 0 Dark-jacket visitor | The Dark-jacket visitor is centrally positioned. | exists |
| S3-spa-2 | 0 Dark-jacket visitor | The Dark-jacket visitor is in the foreground. | exists |
| S3-spa-3 | 0 Dark-jacket visitor | The Dark-jacket visitor is mostly seen from behind. | when_visible |
| S3-spa-4 | 1 Beige-jacket visitor | The Beige-jacket visitor is upright. | exists |
| S3-spa-5 | 1 Beige-jacket visitor | The Beige-jacket visitor is at screen-right. | exists |
| S3-spa-6 | 3 Suited man | The Suited man is standing. | exists |
| S3-spa-7 | 3 Suited man, 9 Wooden office desk | The Suited man stands behind the desk. | exists |
| S3-spa-8 | 3 Suited man, 14 Office windows | The windows form the backdrop behind the Suited man. | exists |
| S3-spa-9 | 14 Office windows | The windows face toward the city. | when_visible |
| S3-spa-10 | 11 Open black laptop | The laptop is open. | when_visible |
| S3-spa-11 | 11 Open black laptop, 0 Dark-jacket visitor, 1 Beige-jacket visitor, 3 Suited man | The laptop lies between the men in the across-desk composition. | when_visible |
| S3-spa-12 | 16 Metal drinks stand, 14 Office windows | The drinks stand is beside the windows. | when_visible |

**motion** (4)

| id | entities | expected | quantifier |
|---|---|---|---|
| S3-mot-1 | 3 Suited man | The Suited man gestures near his chest. | exists |
| S3-mot-2 | 3 Suited man, 0 Dark-jacket visitor, 1 Beige-jacket visitor | The Suited man points toward the visitors. | exists |
| S3-mot-3 | 3 Suited man | The Suited man brings his hands toward his jacket. | exists |
| S3-mot-4 | 0 Dark-jacket visitor | The Dark-jacket visitor extends his right arm toward screen-right at the end. | end |

## Shot4

- **locations**: 5 Office
- **camera_view**: The two visitors are framed from about the waist up against the office's gray paneled doorway.
- **camera_movement**: None
- **transition_from_previous**: cut
- **presence**: 0 Dark-jacket visitor, 1 Beige-jacket visitor, 2 Doorway woman, 4 Hallway, 5 Office, 6 Office double doors, 19 Office doorway, 20 Hallway sconce, 21 Framed black line portrait

**appearance** (0)

(none)

**spatial** (11)

| id | entities | expected | quantifier |
|---|---|---|---|
| S4-spa-1 | 1 Beige-jacket visitor | The Beige-jacket visitor stands. | exists |
| S4-spa-2 | 0 Dark-jacket visitor | The Dark-jacket visitor stands. | exists |
| S4-spa-3 | 1 Beige-jacket visitor | The Beige-jacket visitor is on screen-left. | exists |
| S4-spa-4 | 0 Dark-jacket visitor | The Dark-jacket visitor is on screen-right. | exists |
| S4-spa-5 | 0 Dark-jacket visitor, 1 Beige-jacket visitor, 19 Office doorway | The office doorway forms the backdrop behind the visitors. | exists |
| S4-spa-6 | 2 Doorway woman, 0 Dark-jacket visitor, 1 Beige-jacket visitor | The woman is behind the visitors. | exists |
| S4-spa-7 | 2 Doorway woman, 4 Hallway | The woman is in the hallway. | exists |
| S4-spa-8 | 2 Doorway woman, 5 Office | The woman looks into the office. | exists |
| S4-spa-9 | 0 Dark-jacket visitor | The Dark-jacket visitor faces forward. | exists |
| S4-spa-10 | 6 Office double doors | The visible office door is open. | when_visible |
| S4-spa-11 | 20 Hallway sconce, 4 Hallway | The sconce is in the hallway. | when_visible |

**motion** (8)

| id | entities | expected | quantifier |
|---|---|---|---|
| S4-mot-1 | 0 Dark-jacket visitor, 2 Doorway woman | The Dark-jacket visitor gestures back toward the woman. | exists |
| S4-mot-2 | 0 Dark-jacket visitor | The Dark-jacket visitor turns his head. | exists |
| S4-mot-3 | 0 Dark-jacket visitor | The Dark-jacket visitor lowers his arm. | exists |
| S4-mot-4 | 2 Doorway woman, 5 Office | The woman turns away from looking into the office. | exists |
| S4-mot-5 | 2 Doorway woman, 4 Hallway | The woman walks farther down the hallway. | exists |
| S4-mot-6 | 1 Beige-jacket visitor, 0 Dark-jacket visitor | The Beige-jacket visitor glances toward the Dark-jacket visitor. | exists |
| S4-mot-7 | 1 Beige-jacket visitor, 19 Office doorway | The Beige-jacket visitor turns toward the doorway. | exists |
| S4-mot-8 | 0 Dark-jacket visitor | The Dark-jacket visitor turns his head left; the source does not specify whether left is screen-relative or his own left. | exists |

## unresolved

- Shot4's 'turns his head left' does not specify screen-left versus the Dark-jacket visitor's anatomical left; retain the directional wording without imposing a frame.
- The framed black line portrait in Shot4 is not explicitly identified with the office art in earlier shots; its separate registry entry must not be interpreted as certainty that it is physically distinct.

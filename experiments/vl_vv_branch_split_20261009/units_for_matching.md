## runs/main/run_a/p002_wan21
- L1 [v_l/presence_count] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3中，画面右前景边缘未见暗色虚焦形状，与“the blurred dark shape stays at the right foreground edge”的要求不符。 | ents: Dark foreground shape:s
- L2 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4中男子穿深蓝灰色有领、带门襟扣子的衬衫，而全片人物描述要求他穿褪色蓝灰T恤；服装类型不符。 | ents: Bearded man:s | REV: 将原描述聚焦为可见且明确的核心差异：Shot4是有领扣襟衬衫，而要求是T恤；不将颜色差异作为判定依据。
- V1 [cross_shot/character_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一名男子在Shot1–3与Shot4的面部身份外观不一致：Shot4的面部轮廓与五官呈现不同；卷发造型也不同。 | ents: Bearded man:s/prompt_bound | REV: 将重点明确为跨镜头面部身份不一致，并保留卷发外观差异作为伴随观察。
- V2 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一男子在Shot1–3穿蓝灰色短袖圆领T恤，Shot4则穿蓝灰色有领、带门襟的衬衫；镜头中未见换装过程。 | ents: Bearded man:s/prompt_bound
- V3 [cross_shot/object_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | Shot1–3所见沙发背部较低、横向平直；Shot4同一米色沙发呈高大圆弧包覆式背部，结构明显不同。 | ents: Beige sofa:s/prompt_bound

## runs/main/run_a/p014_storymem

## runs/main/run_a/p014_wan21
- L1.1 [v_l/attribute] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中男子戴黑色宽檐帽，而非要求的黑色耳罩帽。 | ents: 戴帽老人:s | split
- L1.2 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4中男子戴黑色宽檐帽，而非要求的耳罩帽。 | ents: 戴帽老人:s | split
- L2 [v_l/action_state] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中男子后段将一只手从口袋抬到帽边，违反全程把手放在口袋里的要求。 | ents: 戴帽老人:s
- L3.1 [v_l/action_state] Shot3 confirmed/requirement_violated/medium sev=moderate | Shot3中女子全程可见的嘴唇保持闭合，未呈现从微张到闭合的动作。 | ents: 灰外套女性:s | split | REV: 明确问题是镜头中缺少从微张到闭合的动作；原摘要提到的微张起始状态也未在关键帧中显示。
- L3.2 [v_l/action_state] Shot3 confirmed/requirement_violated/medium sev=moderate | Shot3中女子头部姿态几乎不变，未见要求的轻微倾头。 | ents: 灰外套女性:s | split
- L4 [v_l/spatial_orientation] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4开头男子背对镜头，只见后脑和背部；不符合起始时低头并呈屏幕左向侧面的要求。 | ents: 戴帽老人:s
- V1 [cross_shot/character_appearance] Shot2,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一女性在Shot2第5帧穿灰色系带大衣，露出浅桃色高领且没有围巾；Shot3第0帧则穿灰色双排扣大衣并围浅驼色围巾，服装细节不一致。 | ents: 灰外套女性:s/prompt_bound | REV: 将原描述中的衣物差异具体化为系带款与双排扣款、浅桃色高领与浅驼色围巾，并明确比较帧。

## runs/main/run_a/p028_wan22
- L1 [v_l/interaction] Shot2 confirmed/requirement_violated/high sev=major | Shot2中，女子没有用自己抬起的手轻托伸入画面的手腕，未实现要求的支撑动作。 | ents: Turquoise woman:s, Incoming hand owner:s
- L2 [v_l/spatial_orientation] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3右侧的蓝色椅子呈近处、占画面较大区域的物体，而不是要求的远处小椅子。 | ents: Blue beach chair:s
- L3.1 [v_l/attribute] Shot7 confirmed/requirement_violated/medium sev=moderate | Shot7右后方的蓝椅轮廓清楚可辨，未呈现为模糊背景中的椅子。 | ents: Blue beach chair:s | split | REV: 将候选中“尺寸很大”的说法修正为帧中可见的清晰可辨；此单元仅判断模糊度。
- L3.2 [v_l/spatial_orientation] Shot7 rejected/requirement_satisfied/high sev=none | Shot7的蓝椅位于远右背景且尺度较小，并未显示为近处的大型椅子。 | ents: Blue beach chair:s | split | REV: 将候选所称“大尺寸”修正为帧中实际可见的远右背景小椅；该部分不构成违背合同描述。
- V1.1 [cross_shot/character_appearance] Shot2,Shot4,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=major | 同一青衣女子在Shot2的上衣可见区域基本为纯青绿色，而Shot4、Shot6和Shot8的上衣均可见明显深色图案；这些镜头间未见换衣等变化。 | ents: Turquoise woman:s/prompt_bound | split | REV: 将候选笼统的“上衣图案”明确为Shot2与后续镜头的可见差异，并指出Shot4、Shot6、Shot8均有深色图案。
- V1.2 [cross_shot/character_appearance] Shot2,Shot6 confirmed/inconsistency_confirmed/medium sev=moderate | 同一青衣女子在Shot2的棕色肩长波浪发仅有较不显眼的浅色发丝；Shot6的头发则呈现显著浅色挑染条纹，发色外观不一致。 | ents: Turquoise woman:s/prompt_bound | split | REV: 将候选笼统的发型差异改为可从所给画面直接比较的浅色挑染显著程度差异；不将风吹造成的发丝形态变化误作发型改变。
- V2 [cross_shot/object_identity] Shot1,Shot3,Shot5,Shot7 rejected/not_expected_to_match/medium sev=none | 候选所指蓝色椅子在Shot1、Shot5的画面中是远处小型直立椅，而Shot3、Shot7中可见宽大的蓝色躺椅；候选将后者与前者视为同一把椅子。 | ents: Blue beach chair:s/prompt_bound | REV: 明确指出Shot3、Shot7中的宽躺椅与Shot1、Shot5的小型直立椅在可见外形上不同，并按画面可辨的家具类型描述。

## runs/main/run_a/p032_wan22
- L1 [v_l/spatial_orientation] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中男子位于烤箱右侧，而要求是男子站在烤箱左侧。 | ents: 格纹衬衫男子:s, 内嵌烤箱:s
- L2 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中浅色烤箱把手位于画面左侧，而要求把手和发光窗位于画面右侧；烤箱本体位于左侧并非文本所规定的位置。 | ents: 内嵌烤箱:s, Oven handle:s | REV: 将未被要求规定的烤箱本体方位从问题核心中剔除，保留明确要求但位置错误的把手问题。
- L3 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中发光烤箱窗位于画面左侧，而要求发光窗位于画面右侧。 | ents: Oven window:s
- L4 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中浅色烤箱把手位于画面左侧，而要求把手位于画面右侧。 | ents: Oven handle:s
- V1 [cross_shot/character_appearance] Shot1,Shot3,Shot6 confirmed/inconsistency_confirmed/high sev=major | 同一男子的衬衫跨镜头格纹尺度及明暗、配色不一致：Shot1呈较细的灰蓝白格，Shot3呈更大且黑白反差明显的格纹，Shot6又呈深蓝白细格。 | ents: 格纹衬衫男子:s/prompt_bound | REV: 补充Shot6并将差异具体表述为格纹尺度及明暗、配色的变化。
- V2 [cross_shot/setting_background] Shot1,Shot3,Shot5 rejected/normal_change/medium sev=none | 厨房背景在Shot1、Shot3和Shot5之间呈现不同的柜体外观与色调，且可见拱门布局并不相同；但这些差异可由不同拍摄方向、取景范围及光照解释。 | ents: 厨房墙面与柜体结构:s/prompt_unbound, 厨房柜体:s/prompt_bound, 厨房:c/prompt_bound | REV: 保留候选指出的背景差异，同时明确Shot5中拱门不在画面内不能单独证明其布局改变。
- V3 [cross_shot/object_identity] Shot3,Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=major | 同一厨房的内嵌烤箱外观跨Shot3、Shot4和Shot5不一致：Shot3及Shot5可见带玻璃门、横把手和控制面板的烤箱，而Shot4画面左侧出现带通风孔、外形明显不同的设备。 | ents: 内嵌烤箱:s/prompt_bound, 厨房:c/prompt_bound | REV: 明确比较Shot3、Shot4和Shot5中可见的烤箱差异，并描述其可辨认的外观特征。

## runs/main/run_a/p047_storymem
- L1 [v_l/spatial_orientation] Shot8 confirmed/requirement_violated/high sev=moderate | Shot8中，文字要求无袖男子抬起的裸臂部分裁切在画面左上缘；但画面中裸臂出现在画面右上缘，位置与要求相反。 | ents: Sleeveless man:s
- V1 [within_shot/rendering_instability] Shot6 rejected/normal_change/high sev=none | Shot6第0帧近景前景出现橙褐色严重失焦遮挡，遮住老者；第1帧起画面清晰可见老者与背景。 | ents: Older man:c/prompt_bound, Sleeveless man:c/prompt_bound | REV: 将“全画面”改为准确描述前景近距离遮挡，并补充其与第1帧清晰画面的对比。

## runs/main/run_a/p047_wan21
- L1 [v_l/action_state] Shot1 confirmed/requirement_violated/high sev=major | Shot1中男子没有按“向下从画面底部退出”的要求离开；画面显示他移向门洞并在门洞内翻转腾空，之后才消失。 | ents: White-clad man:s | REV: 更正为依据完整镜头指出男子朝门洞移动并在画面内翻转，而不只是未从底部退出。
- L2.1 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4左侧的马尾男子可见浅色短发，并未呈现契约所述在颈后扎起的深色后梳头发。 | ents: Ponytailed man:s | split | REV: 将概括性的发型不符明确为可见头发颜色和长度/扎发特征与契约描述不符。
- L2.2 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4左侧马尾男子赤裸上身、仅穿黑裤，没有按“Both men in black”的要求穿黑色上衣或黑色武术服。 | ents: Ponytailed man:s | split | REV: 明确限定为左侧男子缺少黑色上衣；镜头中右侧男子穿黑色无袖上衣，因此问题并非两人都未着黑。
- L3 [v_l/action_state] Shot6 confirmed/requirement_violated/high sev=major | Shot6没有呈现无袖男子裸臂横过近景、短暂遮挡年长男子脸部和胸部、再从画面中心移开的指定动作；所见前景手臂维持在画面左侧竖直位置，未遮住年长男子脸胸。 | ents: Sleeveless man:s | REV: 补充说明可见手臂持续位于左侧前景，且年长男子脸胸未被遮挡。
- V1.1 [cross_shot/instance_count] Shot3,Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=major | Shot4左侧浅棕发、裸上身的男子与Shot3及Shot5中黑发束发、穿黑色武术服的马尾男子外观不符；同一角色的外观在Shot4发生错位。 | ents: Ponytailed man:s/prompt_bound, Sleeveless man:s/prompt_bound | split | REV: 明确为Shot4左侧人物与Shot3/5马尾男子的外观对应错误；证据主要支持身份/外观互换，而非单纯面部变化。
- V1.2 [cross_shot/instance_count] Shot4,Shot5,Shot7 confirmed/inconsistency_confirmed/high sev=major | Shot4右侧黑发后束、穿黑色无袖制服的男子与Shot5及Shot7中短浅棕发、穿黑色无袖制服的男子外观身份不符；Shot4中两名角色的可见外观呈互换状态。 | ents: Ponytailed man:s/prompt_bound, Sleeveless man:s/prompt_bound | split | REV: 将描述明确为Shot4右侧人物与Shot5/7无袖男子的外观对应错误，并保留与另一角色互换的核心问题。
- V2.1 [cross_shot/setting_background] Shot2,Shot6,Shot8 confirmed/inconsistency_confirmed/medium sev=major | 训练室背景在Shot2呈木色墙面及深色横向饰带，而Shot6/8呈浅色墙面与蓝灰色下墙带；这些背景外观不一致。 | ents: 木色墙面:s/prompt_unbound, Martial arts training room:c/prompt_bound | split | REV: 准确描述可见的墙面差异，避免将Shot2的木墙直接断定为Shot6/8同一墙面。
- V2.2 [cross_shot/setting_background] Shot4,Shot7 rejected/normal_change/medium sev=none | Shot4全景中的训练室背景与Shot7近景所见旗帜及浅色墙面布局未能直接对应；但不同取景方向可解释画面中可见背景区域不同。 | ents: 木色墙面:s/prompt_unbound, Martial arts training room:c/prompt_bound | split | REV: 将候选的确定性不兼容表述改为核查Shot4/7的不同背景取景是否构成矛盾。

## runs/main/run_a/p069_wan21
- L1 [v_l/spatial_orientation] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中男子前进时没有把枪举到脸前；所见枪械始终处于躯干前方，后段横在胸前，未实现“he moves forward with the large gray-and-black Angular firearm raised before his face”的位置要求。 | ents: Red-and-black jacket man:s, Angular firearm:s
- L2 [v_l/attribute] Shot2 confirmed/requirement_violated/high sev=minor | Shot2灰棕色长外套成人的下装可见为暗红色，而非要求的深色长裤；这与“over dark trousers”不符。 | ents: Long-coat adult:s
- L3 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4参与搏斗的长外套成人所穿外套呈橄榄绿，而非合同要求的宽松灰棕色外套。 | ents: Long-coat adult:s
- L4 [v_l/attribute] Shot4 rejected/requirement_satisfied/high sev=none | Shot4左侧短衣人物可见棕色调长裤，符合短人物穿棕色调裤子的要求；没有证据表明其裤子颜色违反描述。 | ents: Short dark-clothed figure:s | REV: 将候选声称的“深色而非棕色”修正为帧中可见的棕色调裤装，并按核心问题判断其是否违反要求。
- V1 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一男主在Shot1帧4穿红黑菱纹夹克，内搭黑色高领衣；Shot3帧0则穿红黑细横纹高领上衣，夹克款式与图案不一致。 | ents: Red-and-black jacket man:s/prompt_bound | REV: 明确区分Shot1的菱纹夹克及黑色内搭与Shot3的细横纹上衣。
- V2 [cross_shot/setting_background] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=major | Shot1帧4的走廊背景可见红砖与剥落绿漆墙、旧楼梯和右侧旧绿门；Shot3帧0回返画面则呈现亮绿砌块墙及不同样式的楼梯，背景结构与材质不匹配。 | ents: 走廊墙面:s/prompt_bound, 走廊楼梯:s/prompt_bound, Industrial corridor:c/prompt_bound | REV: 将差异具体表述为墙面、楼梯及Shot1可见旧门的背景不匹配。
- V3 [cross_shot/object_identity] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 男主在Shot1帧5持有宽厚纹理灰黑枪身、带瞄准镜的枪械；Shot3帧0持有灰色机匣、细长枪管并带醒目黄色挂带的枪械，结构及配件不同。 | ents: Angular firearm:s/prompt_bound | REV: 补充Shot1瞄准镜及Shot3黄色挂带等可辨别差异。
- V4 [cross_shot/character_identity] Shot2,Shot4 confirmed/inconsistency_confirmed/high sev=major | Shot2帧4的短装人物呈短发女性样貌；Shot4帧4左侧短装人物则呈短发男性样貌，面部外观与身份不一致。 | ents: Short dark-clothed figure:s/prompt_bound
- V5 [cross_shot/character_appearance] Shot2,Shot4 confirmed/inconsistency_confirmed/high sev=major | Shot2帧4的面罩人物戴红黑头盔，穿长款红黑外衣及黑靴；Shot4帧4同一人物为红色面罩，服装呈红色主体与深蓝色区域，头部覆盖物及服装外观不一致。 | ents: Red-suited masked adult:s/prompt_bound | REV: 明确Shot4可见的是红色面罩及红/深蓝服装分区。
- V6 [cross_shot/character_appearance] Shot2,Shot4 confirmed/inconsistency_confirmed/high sev=major | Shot2帧4的长外套人物为直发，穿灰色外套与红色长裤；Shot4帧4与面罩人物搏斗的长外套人物则为卷发，穿橄榄绿外套与深色裤，发型及服装不一致。 | ents: Long-coat adult:s/prompt_bound

## runs/main/run_b/p002_wan21
- L1 [v_l/setting_environment] Shot2,Shot3 confirmed/requirement_violated/high sev=moderate | Shot2与Shot3的房间画面都明显明亮；这与房间应为昏暗的描述相矛盾。 | ents: Warm room:s | REV: 将候选所说的明亮室内具体表述为画面中的房间照明明亮；保留Shot2、Shot3两个发生该问题的镜头。
- L2 [v_l/presence_count] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3画面右侧前景没有可见的模糊深色形状，尽管镜头文字要求该形状停留在画面右侧前景边缘。 | ents: Dark foreground shape:s
- L3 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4男子穿着深色有领、带门襟的衬衫，而合同要求该男子穿褪色蓝灰色T恤。 | ents: Bearded man:s | REV: 明确指出画面可见的是深色有领衬衫，与合同要求的T恤类型及颜色描述不符。
- V1.1 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一男子在Shot1至Shot3穿蓝灰色圆领短袖T恤，而Shot4穿深蓝灰色有领衬衫，服装类型与颜色均不一致。 | ents: Bearded man:s/prompt_bound | split | REV: 将差异明确为T恤与有领衬衫的跨镜头变化，并避免将前三镜头描述为完全相同的服装细节。
- V1.2 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/medium sev=moderate | 同一男子在Shot1至Shot3呈较蓬松、较长的卷发外观，Shot4则为更短、更贴头的卷发，发型长度和轮廓不一致。 | ents: Bearded man:s/prompt_bound | split | REV: 将原描述中前三镜头发型完全一致的说法收窄为可见的蓬松度、长度与轮廓差异。
- V2 [cross_shot/character_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | Shot4中的男子与Shot1至Shot3中反复出现的男子面部身份不一致，面部轮廓、肤色观感及五官比例有明显变化。 | ents: Bearded man:s/prompt_bound
- V3 [cross_shot/object_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一浅米色沙发在Shot1至Shot3呈低矮、近直线的靠背轮廓，Shot4则呈明显高起的圆弧形靠背，外形不一致。 | ents: Beige sofa:s/prompt_bound

## runs/main/run_b/p014_storymem
- L1 [v_l/attribute] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中，文字要求背景为“thick pollarded trees”；画面中的背景树木是枝叶自然伸展的常绿针叶树，没有可见的修剪树形，因此不符合“pollarded”的要求。 | ents: Courtyard trees:s | REV: 明确问题在于树木未呈现 pollarded 修剪树形；画面可见常绿针叶树及自然伸展的枝叶。
- V1 [within_shot/unintended_cut] Shot4 rejected/normal_change/high sev=none | Shot4 f0至f1中人物由低头弯身姿态转为较直立、抬起面部；树干及背景位置基本不变，未见机位或构图突然跳变。 | ents: Courtyard:c/prompt_bound | REV: 修正候选将人物姿态变化误判为镜头跳切；关键帧中背景和树干布局基本一致。

## runs/main/run_b/p014_wan21
- L1 [v_l/attribute] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中男子戴着黑色宽檐帽，未见耳罩结构，与要求的黑色耳罩帽不符。 | ents: 戴帽年长男子:s
- L2 [v_l/action_state] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2后段男子一只手离开口袋并抬到帽边，因此没有全程把双手留在口袋。 | ents: 戴帽年长男子:s
- L3 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4男子戴着黑色宽檐帽而非耳罩帽，未见耳罩结构。 | ents: 戴帽年长男子:s
- L4 [v_l/spatial_orientation] Shot4 confirmed/requirement_violated/high sev=major | Shot4开头男子背对镜头，主要可见后脑和背部，不是要求的脸部低垂、屏幕左侧面起始姿态。 | ents: 戴帽年长男子:s
- V1.1 [cross_shot/character_appearance] Shot1,Shot2,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一女子在Shot1与Shot2穿着系带或敞开的灰色外套；Shot3则穿着带明显双排扣的灰色外套，外套结构不一致。 | ents: 灰外套女子:s/prompt_bound | split | REV: 将原先笼统的外观差异明确为外套结构差异；依据画面把Shot2描述为敞开外套。
- V1.2 [cross_shot/character_appearance] Shot1,Shot2,Shot3 confirmed/inconsistency_confirmed/high sev=minor | 同一女子在Shot1和Shot2颈部可见浅桃色衣物，Shot3则在颈部多出浅棕色围巾，构成无可见原因的配饰差异。 | ents: 灰外套女子:s/prompt_bound | split | REV: 将原描述中“加浅棕围巾”明确为与Shot1、Shot2颈部可见浅桃色衣物相比，Shot3出现浅棕围巾。

## runs/main/run_b/p028_wan22
- L1 [v_l/spatial_orientation] Shot1 rejected/requirement_satisfied/high sev=none | Shot1中女子一只手靠近耳侧，后续画面中手指移至下巴附近；未能确认整段都维持文字所述的手指位置。 | ents: Robe woman:s | REV: 修正候选所称“未形成姿势”：Shot1后段可见手指靠近下巴，因此并非整段都缺少该位置。
- L2 [v_l/interaction] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中来手触及女子脸颊，但画面未见女子抬起自己的手托住来手手腕，未实现文字要求的支撑接触关系。 | ents: Turquoise woman:s, Incoming hand owner:s
- L3 [v_l/attribute] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3右侧蓝色沙滩椅在画面中较大且轮廓清楚，并非合同所述在女子视角中位于右侧远处的小椅。 | ents: Blue beach chair:s
- L4 [v_l/attribute] Shot6 confirmed/requirement_violated/high sev=moderate | Shot6中女子的嘴唇可见张开，没有在镜头时段内保持闭合，违背文字要求。 | ents: Turquoise woman:s
- L5 [v_l/action_state] Shot7 rejected/requirement_satisfied/high sev=none | Shot7女子先张开嘴，随后在镜头后段将嘴闭合；候选所称末帧仍明显张嘴与画面不符。 | ents: Robe woman:s | REV: 更正末帧观察：Shot7末帧嘴部已闭合或接近闭合，而不是仍明显张开。
- L6 [v_l/attribute] Shot7 confirmed/requirement_violated/high sev=moderate | Shot7右侧背景中的蓝色椅子较大且轮廓清楚，不符合合同所述位于右侧远处的小椅；也与本镜头要求椅子模糊的描述不符。 | ents: Blue beach chair:s
- V1 [cross_shot/character_appearance] Shot2,Shot4,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=major | 青衣女子的上衣图案在不同镜头间不一致：Shot2中为基本纯色的青绿色上衣（可见深色肩带，但没有明显衣身印花）；Shot4中出现胸前零散深色标记；Shot6中可见不同位置和形状的深色标志；Shot8则为明显的深色棕榈状印花。镜头之间没有可见换装过程。 | ents: Turquoise woman:s/prompt_bound | REV: 将含混的“不同深色图案/标记”具体说明为各镜头可见的衣身图案差异，并区分Shot2的深色肩带与衣身印花。

## runs/main/run_b/p032_wan22
- L1 [v_l/action_state] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2要求人物短暂将双手合拢后放下；画面中可见双手合拢，但随后一直维持合拢姿势，未呈现放下动作。 | ents: 格纹衬衫男子:s | REV: 修正为合手动作出现、但未见随后放下，聚焦候选所述动作序列中未完成的部分。
- L2 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2要求发光的烤箱窗位于画面右侧，但窗实际位于画面左侧。 | ents: Oven window:s
- L3 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2要求浅色烤箱把手位于画面右侧，但把手实际位于画面左侧。 | ents: Oven handle:s
- L4 [v_l/attribute] Shot6 rejected/requirement_satisfied/high sev=none | Shot6要求出现一只短毛白猫；画面中的猫以白色为主，但带有明显黑色尾巴和黑色斑块。黑色斑块不与“白猫”这一描述矛盾。 | ents: 白猫:s | REV: 明确候选观察到的黑色斑块与黑尾，同时指出它们不足以否定画面中的猫是白猫。
- L5 [v_l/action_state] Shot6 rejected/requirement_satisfied/high sev=none | Shot6要求猫越过桌边后从桌面下方消失出视野。画面中猫逐步移向右侧，末帧已看不到猫；候选所称末帧仍有身体部分可见不成立。 | ents: 白猫:s | REV: 更正末帧观察：猫在末帧已不可见，而非仍有身体部分露出。
- V1 [cross_shot/object_identity] Shot3,Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=major | 同一厨房内置烤箱在Shot3、Shot4和Shot5的可见外观不一致：Shot3为黑色玻璃门烤箱，Shot4左侧可见带通风孔的黑色设备，Shot5则为带棕色控制面板和白色粗把手的玻璃烤箱。 | ents: 内置烤箱:s/prompt_bound, 厨房:c/prompt_bound | REV: 明确列出三镜头中烤箱外观差异；Shot4仅能观察到其左侧带通风孔的部分。
- V2.1 [cross_shot/setting_background] Shot1,Shot3,Shot4 confirmed/inconsistency_confirmed/medium sev=moderate | 厨房墙面及其相邻固定背景在Shot1、Shot3、Shot4之间外观不一致：Shot1和Shot4可见青绿色墙面与琥珀拱门，Shot3则呈现浅色柜体、拱门及烤箱构成的另一种背景布局。 | ents: 厨房墙面:s/prompt_unbound, 厨房柜体:s/prompt_bound, 厨房:c/prompt_bound | split | REV: 将墙面/拱门背景作为一个单位，限定到候选所述的Shot1、Shot3、Shot4背景差异；未将柜体差异混入本单位。
- V2.2 [cross_shot/setting_background] Shot2,Shot3,Shot5 confirmed/inconsistency_confirmed/high sev=moderate | 厨房柜体在Shot2、Shot3和Shot5之间外观与构成不一致：Shot2和Shot5以橙色柜体为显著背景，Shot3则显示浅色上柜。 | ents: 厨房墙面:s/prompt_unbound, 厨房柜体:s/prompt_bound, 厨房:c/prompt_bound | split | REV: 将柜体颜色及构成差异独立成单位，并使用候选已有的Shot2、Shot3、Shot5作为对照。

## runs/main/run_b/p047_storymem
- L1 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4中马尾男子没有按要求举手进入防守姿势；末帧可见其双臂垂在身侧。 | ents: Ponytailed man:s
- L2 [v_l/attribute] Shot4 rejected/requirement_satisfied/high sev=none | 候选称Shot4地面呈蓝色而非酒红色；但要求所指的右前景地面（白衣男子躺卧处）呈酒红色，画面中的蓝色区域是室内垫子。 | ents: Training room floor:s | REV: 更正候选对地面颜色的判断：蓝色区域为垫子；要求所指的右前景地面实际为酒红色。
- V1 [within_shot/rendering_instability] Shot6 confirmed/inconsistency_confirmed/high sev=major | Shot6第0帧整幅画面出现严重模糊拖影及暗色遮挡，主体和背景几乎不可辨；到第1帧画面骤然恢复清晰，构成无可见成因的首帧渲染闪变。 | ents: 

## runs/main/run_b/p047_wan21
- L1 [v_l/action_state] Shot1 confirmed/requirement_violated/high sev=major | Shot1中男子没有按要求向下从画面底部退出；他转向门洞并在门洞内腾空翻转，之后画面才显示空出的墙面。 | ents: White-clad man:s
- L2 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4左侧马尾男子上身赤裸、只穿黑裤，没有穿合约要求的黑色武术服。 | ents: Ponytailed man:s
- L3 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4左侧马尾男子没有呈现短暂前屈后直起的动作，而是在镜头中腾跃并迈步。 | ents: Ponytailed man:s
- L4 [v_l/action_state] Shot5 confirmed/requirement_violated/high sev=moderate | Shot5马尾男子没有保持弯身防守姿态，也没有一只手靠近胸口；画面中他基本直立，双臂垂在身体两侧。 | ents: Ponytailed man:s
- V1 [cross_shot/character_appearance] Shot2,Shot6,Shot8 rejected/consistent_in_frames/high sev=none | Older man在Shot2、Shot6和Shot8的灰发看起来均为向后梳理并在颈后束起；没有足够可见证据表明Shot6或Shot8发长、束发状态与Shot2不相容。 | ents: Older man:s/prompt_bound | REV: 修正候选所称Shot6、Shot8为短发的判断；可见发型与Shot2相符。
- V2 [cross_shot/character_appearance] Shot3,Shot4,Shot5 rejected/not_expected_to_match/high sev=none | Shot3和Shot5中的Ponytailed man是深色低马尾、穿黑色武术服；Shot4左侧人物是短浅棕发、赤裸上身的另一男子，并非同一人物。Shot4中与其相符的马尾男子在画面右侧。 | ents: Ponytailed man:s/prompt_bound | REV: 纠正Shot4人物对应：候选把左侧短发赤裸上身男子误认作Ponytailed man；画面右侧黑色无袖服、束马尾者才与其对应。
- V3 [cross_shot/character_appearance] Shot4,Shot5,Shot7 rejected/not_expected_to_match/high sev=none | 候选所称Shot4中Sleeveless man为深色长发束起，与Shot5、Shot7的浅色短发不同；但Shot4画面中束马尾、穿黑色无袖服的人是右侧人物，不是左侧短浅棕发的Sleeveless man。 | ents: Sleeveless man:s/prompt_bound | REV: 纠正Shot4人物身份对应：深色马尾男子不应作为Sleeveless man的外观证据；Shot4左侧人物才是短发Sleeveless man。

## runs/main/run_b/p069_wan21
- L1 [v_l/spatial_orientation] Shot1 confirmed/requirement_violated/high sev=major | Shot1中男子前进时，枪始终未举到脸前；关键帧中枪出现在胸前或更低位置，与“raised before his face”的要求不符。 | ents: Red-and-black jacket man:s, Angular firearm:s
- L2 [v_l/setting_environment] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4结尾没有呈现狭窄的绿砖楼梯井；末段可见的是绿色涂漆隔墙和平台区域，而非可辨认的绿砖楼梯井。 | ents: Green-brick stairwell:s
- L3 [v_l/presence_count] Shot4 rejected/requirement_satisfied/medium sev=none | Shot4末段可见右上方斜向的扶手构件，因此候选所称金属扶手缺失不成立；画面没有清楚证明其材质，但没有可见证据表明要求的扶手不存在。 | ents: Diagonal metal handrail:s | REV: 修正“未见金属扶手”的判断：关键帧右上方能看到斜向扶手构件，故按所引的扶手存在要求核验。
- L4.1 [v_l/action_state] Shot4 rejected/requirement_satisfied/medium sev=none | Shot4中两人被带向右侧开口并下降至平台下方；关键帧呈现两人越过平台边缘、进入下方楼梯区域的连续搏斗过程，因此候选所称“未翻滚至平台下”不成立。 | ents: Red-suited masked adult:s, Long-coat adult:s, Stair landing:s | split | REV: 根据关键帧修正候选判断：两人确实越过平台边缘并到达其下方；画面未必呈现完整滚动动作，但可见其向下进入平台下方。
- L4.2 [v_l/interaction] Shot4 rejected/requirement_satisfied/high sev=none | Shot4结尾两人紧密纠缠、彼此搂持并蹲伏在一起；提示词只要求以“tangled bodies”结束，并未要求两人平躺，因此候选所称末帧不是纠缠状态不成立。 | ents: Red-suited masked adult:s, Long-coat adult:s, Stair landing:s | split | REV: 澄清结尾要求：提示词要求纠缠的身体，不要求倒地平躺；末帧可见两人仍相互缠抱。
- V1 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一红黑夹克男子在Shot1与Shot3穿着的夹克纹样不同：Shot1为红黑菱形纹，Shot3为红黑横向纹；两镜头之间没有可见换装动作。 | ents: Red-and-black jacket man:s/prompt_bound
- V2.1 [cross_shot/character_identity] Shot2,Shot4 confirmed/inconsistency_confirmed/high sev=major | Shot2与Shot4被识别为长外套成人的人物外观不一致：Shot2出现短棕发、女性化面貌的灰外套人物；Shot4对应位置出现短发男性、深色外套人物。 | ents: Long-coat adult:s/prompt_bound | split | REV: 将面部身份与服装变化拆开；明确Shot2和Shot4呈现的人物面貌差异。
- V2.2 [cross_shot/character_appearance] Shot2,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 长外套成人在Shot2与Shot4的服装不一致：Shot2为灰色外套及暗红裤，Shot4为深色外套及深色裤。 | ents: Long-coat adult:s/prompt_bound | split | REV: 将服装差异从人物身份差异中分离，并以画面中可辨的颜色描述Shot4服装。
- V3 [cross_shot/object_identity] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=major | 主角在Shot1与Shot3持有的同一枪械外形不同：Shot1为黑灰色、粗大且有纹理的枪身；Shot3为银灰色机匣、细长枪管，并带醒目的黄色吊带。 | ents: Angular firearm:s/prompt_bound, Red-and-black jacket man:c/prompt_bound
- V4.1 [cross_shot/setting_background] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | Shot1与Shot3返回的走廊墙面不一致：Shot1可见红砖墙及剥落绿漆；Shot3可见亮绿色砌块墙。 | ents: Industrial corridor:c/prompt_bound, Worn staircase:s/prompt_bound | split | REV: 将墙面差异与楼梯结构差异拆开，明确比较的是墙面材质和颜色。
- V4.2 [cross_shot/setting_background] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=major | Shot1与Shot3同一走廊背景中的楼梯结构不同：Shot1显示宽阔、深色、位于主角后方的楼梯；Shot3显示不同布局的绿色楼梯。 | ents: Industrial corridor:c/prompt_bound, Worn staircase:s/prompt_bound | split | REV: 将楼梯结构单独列为一项，避免与墙面差异混在同一单元。

## runs/main_pre_element_gate/run_a/p002_wan21
- L1 [v_l/presence_count] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3未能呈现“the blurred dark shape stays at the right foreground edge”所要求的右前景边缘虚焦暗色形状；画面右侧可见浅色墙面，未见该暗色形状。 | ents: Dark foreground shape:s
- L2 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4中男子穿着深蓝灰色有领衬衫，而非要求的“faded blue-gray T-shirt with small outlined chest lettering”；衣物类型与指定的T恤不符。 | ents: Bearded man:s | REV: 将问题聚焦为画面中可明确辨认的衣物类型不符；不把颜色深浅作为确认依据。
- L3 [v_l/setting_environment] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4画面呈明亮受光的室内环境，不符合提示词要求的“in the dim warm room”中的昏暗要求。 | ents: Warm room:s
- V1 [cross_shot/character_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一名男子在Shot1–3与Shot4的脸型和五官明显不一致：Shot1–3为较长、较窄的脸部轮廓，Shot4则呈现不同的脸型及面部特征。 | ents: Bearded man:s/prompt_bound | REV: 明确指出对比的是Shot1–3与Shot4的面部身份差异。
- V2 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一名男子在Shot1–3与Shot4的发型和上衣外观不一致：Shot1–3为较蓬松的卷发和蓝灰色短袖T恤，Shot4为更短、更紧密的卷发及不同版型、色调的灰蓝色短袖上衣。 | ents: Bearded man:s/prompt_bound | REV: 明确了对比镜头及发型、上衣的可见差异。
- V3 [cross_shot/object_identity] Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一张米色沙发在Shot3与Shot4呈现不同的靠背形态：Shot3可见的是较低、横向延伸的靠背，Shot4则可见明显较高、圆弧形的靠背。 | ents: Beige sofa:s/prompt_bound | REV: 明确了Shot3与Shot4可见靠背形态的对比。

## runs/main_pre_element_gate/run_a/p014_storymem

## runs/main_pre_element_gate/run_a/p014_wan21
- L1 [v_l/attribute] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中男子戴黑色宽檐帽，未见耳罩，不符合“a black earflap hat”的帽型要求。 | ents: Older man in earflap hat:s
- L2 [v_l/action_state] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2后段男子一只手离开口袋并抬至身前，未能全程保持双手在口袋内，违反“ He keeps his hands in his pockets”。 | ents: Older man in earflap hat:s | REV: 明确为后段一只手抬至身前，且引文按原文去除前置空格。
- L3 [v_l/attribute] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3女子嘴唇各帧均闭合，没有呈现要求的微张嘴唇状态“Her slightly parted lips”。 | ents: Woman in gray coat:s
- L4 [v_l/action_state] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3女子嘴唇首尾均闭合，未呈现从微张到闭合的闭唇过程，违反“Her slightly parted lips close”。 | ents: Woman in gray coat:s
- L5 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4男子戴黑色宽檐帽而非耳罩帽，不符合“Older man in earflap hat”的描述。 | ents: Older man in earflap hat:s
- L6 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4首帧男子背对镜头，只见后脑和背部，未呈现要求的起始低垂面部状态“Starting with his face lowered”。 | ents: Older man in earflap hat:s
- L7 [v_l/spatial_orientation] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4起始帧男子背对镜头，没有呈现要求的画面左侧侧脸“screen-left profile”。 | ents: Older man in earflap hat:s
- V1.1 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一女性在Shot1与Shot3穿着的灰色外套款式不一致：Shot1 frame 5为系带、翻领且未见明显扣子的外套；Shot3 frame 5为带醒目黑色双排扣的灰色外套。 | ents: Woman in gray coat:s/prompt_bound | split | REV: 将外套差异单独列出，并以画面可见的系带与黑色双排扣描述款式差异。
- V1.2 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一女性在Shot1与Shot3的颈部服饰不一致：Shot1 frame 5可见浅桃色高领内搭；Shot3 frame 5颈部出现环绕式浅褐/桃色围巾层，外观不同于Shot1的高领内搭。 | ents: Woman in gray coat:s/prompt_bound | split | REV: 将颈部服饰差异与外套差异拆开，并限定为两帧中可见的高领与围巾层外观差别。

## runs/main_pre_element_gate/run_a/p028_wan22
- L1.1 [v_l/action_state] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1首帧中女子头部没有呈现明显低垂的起始姿势，与“Starting with her head lowered”不符。 | ents: Robe woman:s | split | REV: 将候选中多个起始姿势问题拆分，并在本单元仅判断头部低垂要求。
- L1.2 [v_l/action_state] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1首帧中女子双眼明显睁开，而要求起始时眼睛近乎闭合。 | ents: Robe woman:s | split | REV: 将候选中多个起始姿势问题拆分，并在本单元仅判断眼睛近闭要求。
- L1.3 [v_l/spatial_orientation] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中手指没有维持在下巴附近的电话状姿势：frame 0手贴近耳侧而非下巴，后续画格中才移向下巴。 | ents: Robe woman:s | split | REV: 将候选中的手指位置问题单独列出，并修正为从首帧到后续画格可见的位置变化。
- L2 [v_l/action_state] Shot7 confirmed/requirement_violated/high sev=major | Shot7女子张开嘴后，在所示画格中嘴仍明显张开，没有呈现要求的随后闭嘴状态。 | ents: Robe woman:s
- V1 [cross_shot/object_identity] Shot1,Shot3,Shot5,Shot7 confirmed/inconsistency_confirmed/high sev=moderate | 同一蓝色海滩椅在Shot1、Shot3、Shot5中呈小型直立椅状，而Shot7中变为尺寸明显更大的蓝色躺椅，椅面与支架形态均不同。 | ents: Blue beach chair:s/prompt_bound | REV: 明确列出对照镜头，并将差异具体表述为直立椅与大型躺椅的形态和尺寸差异。
- V2.1 [cross_shot/character_appearance] Shot2,Shot4,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=moderate | 同一青衣女子的上衣图案跨镜不一致：Shot2主要是较纯色的青绿色上衣；Shot4和Shot6可见深色标记；Shot8则出现明显、密集的深色图案。 | ents: Turquoise woman:s/prompt_bound | split | REV: 将图案变化单独列出，区分Shot4/6的标记与Shot8更密集的图案。
- V2.2 [cross_shot/character_appearance] Shot2,Shot4,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=moderate | 同一青衣女子在Shot8可见白色长袖内层，而Shot2、Shot4和Shot6中可见的手臂处没有这一白色袖层。 | ents: Turquoise woman:s/prompt_bound | split | REV: 将白色袖层与上衣图案差异分开，并明确比较镜头。

## runs/main_pre_element_gate/run_a/p032_wan22
- L1 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中，要求发亮的烤箱窗位于画面右侧；但第1、5帧的烤箱窗都在画面左侧，未满足右侧位置要求。 | ents: Oven window:s
- L2 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中，要求浅色烤箱把手位于画面右侧；但第1、5帧的把手都在画面左侧，未满足右侧位置要求。 | ents: Oven handle:s
- L3 [v_l/attribute] Shot3 rejected/requirement_satisfied/high sev=none | Shot3要求烤箱关闭；但第0、5帧所见烤箱玻璃门关闭，未出现门敞开或内部暴露的情况，因此候选所称的关闭状态不符并未得到画面支持。 | ents: 内嵌烤箱:s | REV: 更正候选的观察：Shot3第0、5帧显示烤箱门关闭，而不是持续敞开。
- L4.1 [v_l/presence_count] Shot4 confirmed/requirement_violated/high sev=major | Shot4要求男子靠近关闭的烤箱窗，文本指明烤箱；但第0、5帧男子面前显示的是带通风孔的黑色箱体，而非要求的浅色嵌入式烤箱。 | ents: 内嵌烤箱:s, Oven window:s | split | REV: 将候选中“未见所要求的烤箱”的问题单独列为烤箱本体缺失；窗的缺失另列。
- L4.2 [v_l/presence_count] Shot4 confirmed/requirement_violated/high sev=major | Shot4要求男子朝向关闭的烤箱窗；但第0、5帧中黑色带通风孔箱体上未见烤箱门窗。 | ents: 内嵌烤箱:s, Oven window:s | split | REV: 将候选中“未见烤箱窗”的问题与烤箱本体缺失分开，并聚焦于镜头文本要求的烤箱窗。
- L5 [v_l/action_state] Shot6 confirmed/requirement_violated/high sev=major | Shot6要求猫走到桌子的右前沿、将头部和前躯探过桌沿并消失在桌面下方；但第0至5帧所示猫沿桌面向画面右侧移动，最后被右侧灯具遮挡或离开画面，没有显示它从桌沿下方消失。 | ents: White cat:s
- V1 [cross_shot/object_identity] Shot2,Shot3,Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=moderate | 同一厨房中的内嵌烤箱在不同镜头外观不一致：Shot2、Shot3和Shot5可见浅色柜体中的玻璃门烤箱及控制面板；Shot4左侧则出现黑色箱体、带多排通风槽的设备，外观类型与其他镜头的烤箱不符。 | ents: 内嵌烤箱:s/prompt_bound, 厨房:c/prompt_bound | REV: 将原描述中Shot4与Shot2、Shot3、Shot5的对比具体化；Shot2画面中的烤箱控制面板和玻璃门也与Shot3、Shot5相符。

## runs/main_pre_element_gate/run_a/p047_storymem
- V1 [within_shot/rendering_instability] Shot6 confirmed/inconsistency_confirmed/high sev=moderate | Shot6第0帧出现橙色模糊色块并有大面积近黑区域，画面主体与背景难以辨认；第1帧恢复为清晰的Older man和浅色墙近景，构成单帧渲染闪烁。 | ents:  | REV: 将候选描述中的“近乎黑屏”明确为大面积近黑区域；保留第0帧异常、第1帧恢复的核心问题。

## runs/main_pre_element_gate/run_a/p047_wan21
- L1 [v_l/action_state] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中男子没有按“向下掉出画面底部”的要求离开，而是在门洞方向腾空翻转，之后才消失。 | ents: White-clad man:s
- L2 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4左侧马尾男子上身赤裸，只穿黑裤；这不符合“两名男子都穿黑色服装”的要求。 | ents: Ponytailed man:s | REV: 将“左侧男子”明确为Shot4文字所指的马尾男子，并依据画面说明其上身赤裸、穿黑裤。
- L3 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=major | Shot4要求两名穿黑色服装的男子都短暂前弯再挺直，但画面中左侧马尾男子跳跃、迈步，右侧无袖男子移动并举臂，未见两人完成前弯后挺直。 | ents: Ponytailed man:s, Sleeveless man:s
- L4 [v_l/action_state] Shot5 confirmed/requirement_violated/high sev=moderate | Shot5中的马尾男子直立站着，手臂没有保持弯曲护卫姿势，也没有一只手靠近胸口；与要求不符。 | ents: Ponytailed man:s
- L5 [v_l/setting_environment] Shot5 rejected/requirement_satisfied/medium sev=none | Shot5要求镜面上方有暖色光影图案，但画面中镜面上方可见暖色灯带和明亮的暖色光带。 | ents: Mirror wall:s | REV: 修正候选的“未见图案”判断：画面镜面上方可见暖色光带。
- L6 [v_l/interaction] Shot6 confirmed/requirement_violated/high sev=major | Shot6横过近景并遮挡老者的裸臂属于前景中一名赤裸上身、灰发男子，而不是文字指定的无袖男子；指定人物的手臂未按要求横过前景。 | ents: Sleeveless man:s
- V1 [cross_shot/setting_background] Shot5,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=major | 同一训练室在Shot5呈现镜墙及暖木色墙面；Shot6和Shot8则呈现浅色墙面与蓝灰色墙裙，背景风格和构造明显不一致。 | ents: Martial arts training room:s/prompt_bound | REV: 将原先笼统列举Shot1等镜头的表述收窄至可核验的Shot5与Shot6、Shot8，并明确具体背景差异。
- V2 [cross_shot/character_appearance] Shot2,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=major | 同一老人Shot2穿橄榄卡其色带领上衣；Shot6和Shot8则穿浅米卡其色衬衫，带胸袋并露出白色内搭，镜头间未显示换装。 | ents: Older man:s/prompt_bound

## runs/main_pre_element_gate/run_a/p069_wan21
- L1 [v_l/spatial_orientation] Shot1 confirmed/requirement_violated/high sev=major | Shot1 中男子前进时没有将枪举到脸前：可见枪械首次出现时位于躯干前方，后续横在胸前，未呈现“raised before his face”所要求的脸前举枪状态。 | ents: Red-and-black jacket man:s, Angular firearm:s
- L2 [v_l/attribute] Shot4 confirmed/requirement_violated/medium sev=moderate | Shot4 中长外套成人的外套呈橄榄绿／灰绿色，而合同要求其穿宽松灰褐色外套，颜色不符。 | ents: Long-coat adult:s | REV: 将候选所称“橄榄绿色”具体表述为画面中可见的橄榄绿／灰绿色；保留外套颜色与要求不符这一核心问题。
- L3 [v_l/action_state] Shot4 confirmed/requirement_violated/medium sev=major | Shot4 中两人虽在楼梯区域内持续扭斗并最终蹲伏贴身，但未呈现两人“翻滚到平台下方”的动作。 | ents: Long-coat adult:s, Red-suited masked adult:s, Stair landing:s
- L4 [v_l/action_state] Shot4 rejected/requirement_satisfied/high sev=none | Shot4 结尾两人身体贴近并互相缠抱，符合结束于“their tangled bodies”的要求；候选所称“未呈现两人缠结”不成立。 | ents: Long-coat adult:s, Red-suited masked adult:s | REV: 修正候选对结尾姿态的描述：末帧两人虽蹲伏，但身体和手臂相互缠抱，并非未缠结。
- V1.1 [cross_shot/object_identity] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一把由男主持有的枪械在Shot1与Shot3外形不一致：Shot1帧5为宽厚的黑灰枪身，Shot3帧4则为细长枪身并带醒目的黄色吊带。 | ents: Angular firearm:s/prompt_bound | split
- V1.2 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一男主的夹克纹样在Shot1与Shot3不同：Shot1帧5呈红黑菱格纹，Shot3帧4呈红黑细条纹。 | ents: Red-and-black jacket man:s/prompt_bound | split
- V2 [cross_shot/setting_background] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=major | Shot1与Shot3回返走廊的背景布局不一致：Shot1帧4可见左侧裸砖与绿漆墙、后方楼梯；Shot3帧4则呈现包围人物的绿色砖墙及位于画面左侧的楼梯，背景结构和布局不同。 | ents: Corridor brick walls:s/prompt_bound, Industrial corridor:c/prompt_bound | REV: 将笼统的墙体与楼梯差异具体化为两帧可见的墙面和楼梯布局。
- V3 [cross_shot/character_appearance] Shot2,Shot4 rejected/consistent_in_frames/high sev=none | 红面具角色在Shot2帧4与Shot4帧0的服装外观是否不一致：前者为红黑长款服装，后者为红色与深色拼接的套装。 | ents: Red-suited masked adult:s/prompt_bound | REV: 将候选所称的红蓝套装修正为红色与深色拼接；两帧可见的主要配色及服装形态并未显示为独立的不一致。
- V4 [cross_shot/character_appearance] Shot2,Shot4 confirmed/inconsistency_confirmed/medium sev=major | Shot2帧4与Shot4帧0中被识别为Long-coat adult的角色外观不一致：前者为短棕发、灰色外套及暗红裤；后者为卷曲深发、橄榄绿色外套及深色裤。 | ents: Long-coat adult:s/prompt_bound

## runs/main_pre_element_gate/run_b/p002_wan21
- L1 [v_l/attribute] Shot3 rejected/requirement_satisfied/high sev=none | Shot3 中男子穿蓝灰色圆领短袖T恤，符合合同对褪色蓝灰色T恤的要求；画面未显示有领扣襟上衣这一不符情况。 | ents: Bearded man:s | REV: 更正候选对衣物的识别：Shot3可见圆领短袖T恤，不是有领扣襟上衣。
- L2 [v_l/setting_environment] Shot3 confirmed/requirement_violated/medium sev=moderate | Shot3显示浅色墙面和较明亮、偏中性的室内光线，与要求的暖色房间氛围不符。 | ents: Warm room:s
- L3 [v_l/presence_count] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3未显示要求保持在右侧前景边缘的模糊暗色形状；画面中未见该前景形状。 | ents: Dark foreground shape:s | REV: 将候选所称的“暗色形状位于左侧”更正为画面中未见该形状；保留其未满足右侧前景边缘要求这一核心问题。
- L4 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=major | Shot4中男子穿深蓝灰色有领扣襟上衣，而合同要求褪色蓝灰色T恤并有小型轮廓胸前字样。 | ents: Bearded man:s
- V1 [cross_shot/character_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一男子在Shot1–3中为较蓬松的卷发、较长脸型及相应五官；Shot4则呈现短而紧密的卷发、不同的脸型和五官，像是换成了另一人。 | ents: Bearded man:s/prompt_bound | REV: 将笼统的“身份替换”具体化为跨镜头可见的发型轮廓、脸型和五官差异。
- V2 [cross_shot/object_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一米色沙发在Shot1–3中呈现较低、横向延伸的靠背；Shot4中男子身后的靠背高而圆弧包围，外形明显不同。 | ents: Beige sofa:s/prompt_bound | REV: 将“高圆弧包围式靠背”明确为Shot4中可见的靠背外形，并与Shot1–3对照。
- V3 [cross_shot/setting_background] Shot1,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一房间的背景布景在Shot1、Shot3与Shot4间不一致：Shot1和Shot3可见木门及浅色墙面，Shot4人物后方则是大面积深色木质背景，未能与前述房间布置对应。 | ents: Warm room:s/prompt_bound | REV: 具体指出不同镜头可见的门、墙面及深色木背景，避免将单纯视角变化误称为整个房间差异。

## runs/main_pre_element_gate/run_b/p014_storymem
- L1 [v_l/action_state] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中女子没有按要求双臂下垂：画面里她的手臂在身体前方弯曲，双手位于腰腹附近。 | ents: Woman in gray coat:s

## runs/main_pre_element_gate/run_b/p014_wan21
- L1 [v_l/attribute] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中男子戴黑色宽檐帽，未见耳罩，与“a black earflap hat”的要求不符。 | ents: 戴黑帽年长男子:s
- L2 [v_l/action_state] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2后段男子一只手离开口袋并抬到帽檐，违反“ He keeps his hands in his pockets”的要求。 | ents: 戴黑帽年长男子:s
- L3 [v_l/spatial_orientation] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4开场男子背对镜头，脸不可见，初始姿态不是要求的“face lowered in screen-left profile”。 | ents: 戴黑帽年长男子:s
- V1.1 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一女子在Shot1与Shot3所穿灰色外套的结构不同：Shot1为系带、交叠式外套，Shot3可见双排扣；Shot2中外套敞开，未能清楚确认其具体扣合结构。 | ents: 灰外套女子:s/prompt_bound | split | REV: 将外套款式差异限定为Shot1与Shot3可见的结构对比；Shot2的细节不足以作为独立款式证据。
- V1.2 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一女子的领口层次在Shot1与Shot3不同：Shot1可见浅桃色高领针织层，Shot3则有包裹颈部的浅桃色围巾状布层。 | ents: 灰外套女子:s/prompt_bound | split | REV: 把原描述中的领口层次具体化为高领针织层与围巾状包裹层的差别。
- V2.1 [cross_shot/character_appearance] Shot2,Shot4 rejected/normal_change/medium sev=none | 年长男子在Shot2与Shot4的外套深浅看起来不同：Shot2偏棕橄榄色，Shot4偏深棕近黑。 | ents: 戴黑帽年长男子:s/prompt_bound | split | REV: 将颜色差异表述为画面中可见的色调差异，避免把不同光照下的颜色观感当作确定的服装颜色改变。
- V2.2 [cross_shot/character_appearance] Shot2,Shot4 rejected/consistent_in_frames/high sev=none | 年长男子在Shot2与Shot4中的围巾纹样均为棕色系格纹；未见可确认的跨镜纹样改变。 | ents: 戴黑帽年长男子:s/prompt_bound | split | REV: 候选称围巾由条纹变为格纹，但复核帧中Shot2围巾也可见格纹，故将待判差异明确为纹样是否实际不同。

## runs/main_pre_element_gate/run_b/p028_wan22
- L1 [v_l/interaction] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中，女子没有用自己抬起的手托住来手手腕；画面只见从右侧伸入并贴近她脸侧的来手，未见她自己的手与手腕形成支撑接触，与要求不符。 | ents: Turquoise woman:s, Incoming hand owner:s
- L2 [v_l/interaction] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4中，女子没有从下方轻托来手手腕；画面显示白袖来手伸至她耳颊旁，但未见女子自己的手位于手腕下方并轻握或支撑手腕。 | ents: Turquoise woman:s, Incoming hand owner:s
- V1.1 [cross_shot/object_identity] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一蓝色海滩椅在Shot1呈单张直立椅，而Shot3右侧出现两张低矮躺椅组合，形状与数量不一致。 | ents: Blue beach chair:s/prompt_bound | split | REV: 仅保留Shot1与Shot3这一组独立比较，明确差异为椅型和数量。
- V1.2 [cross_shot/object_identity] Shot5,Shot7 confirmed/inconsistency_confirmed/high sev=moderate | 同一蓝色海滩椅在Shot5呈单张直立椅，而Shot7右侧出现两张低矮躺椅组合，形状与数量不一致。 | ents: Blue beach chair:s/prompt_bound | split | REV: 仅保留Shot5与Shot7这一组独立比较，明确差异为椅型和数量。
- V2 [cross_shot/character_appearance] Shot2,Shot4,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=major | 青绿色女子的上衣在Shot2呈素色；Shot4出现散布的暗色斑记，Shot6出现肩部黑色标志，Shot8则为明显的深色棕榈样图案。跨镜头同一上衣的图案与标记不一致。 | ents: Turquoise woman:s/prompt_bound | REV: 补充Shot6肩部标志与Shot8棕榈样图案的具体差异，保留候选所述同一上衣图案变化。
- V3 [cross_shot/character_appearance] Shot2,Shot4 rejected/normal_change/high sev=none | Shot2中入镜手臂可见裸露前臂；Shot4中同一入镜手臂连着宽大的白袖。 | ents: Incoming hand owner:s/prompt_bound

## runs/main_pre_element_gate/run_b/p032_wan22
- L1 [v_l/spatial_orientation] Shot2 confirmed/requirement_violated/high sev=moderate | Shot2中，文字要求烤箱浅色把手和发亮炉窗位于画面右侧，但画面中二者均位于左侧，违反了位置要求。 | ents: Oven window:s, Oven handle:s
- L2 [v_l/action_state] Shot6 confirmed/requirement_violated/high sev=major | Shot6中，文字要求白猫走向桌面右前缘，低下头和前躯越过桌边，并消失在桌面下方；画面显示猫沿桌面向右移动，随后从画面右侧离开，未呈现低头、前躯越过桌边并从桌面下方消失的动作。 | ents: 白猫:s
- V1.1 [cross_shot/object_identity] Shot1,Shot2,Shot3,Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=major | 同一厨房中的嵌入式烤箱跨镜头外观不一致：Shot1、Shot2及Shot5可见浅色/橙色柜体中的玻璃门烤箱；Shot3则是浅色柜体旁的黑色现代烤箱，Shot4可见带通风孔的深色箱体，外形与前述烤箱明显不同。 | ents: 厨房:c/prompt_bound, 嵌入式烤箱:s/prompt_bound | split | REV: 将烤箱差异单独列为一项，并明确对比镜头及各镜头可见外观；不把画面中的柜体颜色直接等同于烤箱颜色。
- V1.2 [cross_shot/environment_lighting] Shot1,Shot2,Shot3,Shot4,Shot5 rejected/normal_change/high sev=none | Shot4的厨房背景呈明显青蓝色墙面与冷色调，与Shot1、Shot2及Shot5较暖的橙色厨房画面观感不同；背景色差可由Shot4画面中明显的青蓝色照明解释。 | ents: 厨房:s/prompt_bound, 嵌入式烤箱:c/prompt_bound | split | REV: 将背景布景差异与烤箱外观拆开；修正为聚焦Shot4相对其他镜头的色调差异。

## runs/main_pre_element_gate/run_b/p047_storymem
- V1 [within_shot/rendering_instability] Shot6 confirmed/inconsistency_confirmed/high sev=moderate | Shot6第0帧几乎全画面严重模糊并出现橙绿失真色块，场景难以辨认；第1帧起画面恢复清晰、色调正常，形成单帧渲染突变。 | ents: 

## runs/main_pre_element_gate/run_b/p047_wan21
- L1 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=major | Shot4左侧马尾男子上身裸露、仅穿黑色长裤；这与角色描述要求的黑色武术服不符。 | ents: Ponytailed man:s | REV: 将问题限定为可见的上身服装不符，避免把“两名男子穿黑色”误解为每一处衣物都必须为黑色。
- L2.1 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=major | Shot4左侧马尾男子没有按要求短暂弯身后站直；画面中他从站立转为明显的跃动、踢腿动作。 | ents: Ponytailed man:s | split | REV: 拆分出弯身并站直这一组动作要求，单独判断其与跃踢动作的差异。
- L2.2 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4左侧马尾男子没有按要求分开双脚并举手成防守姿势；末帧中他站立、双臂下垂，未形成防守姿势。 | ents: Ponytailed man:s | split | REV: 独立提取分开双脚并举手成防守姿势的要求，并明确末帧可见的不符合之处。
- L3 [v_l/attribute] Shot5 confirmed/requirement_violated/medium sev=moderate | Shot5前景老人的背部穿着浅色、带宽腰带的外衣，未呈现角色描述要求的橄榄卡其色有领衬衫。 | ents: Older man:s | REV: 将颜色表述调整为浅色卡其调，并把可见问题表述为服装形态与角色描述中的有领衬衫不符。
- L4 [v_l/interaction] Shot6 confirmed/requirement_violated/high sev=major | Shot6越过前景并遮挡老人的裸臂连着一名灰发、赤裸上身的人物；画面没有显示它是无袖男子的手臂，因此未呈现要求的无袖男子手臂穿过前景并遮挡老人。 | ents: Sleeveless man:s | REV: 将问题聚焦为前景手臂的可见归属与角色描述不符；避免把手臂后续动作单独作为另一问题。
- V1 [cross_shot/character_appearance] Shot3,Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=major | Ponytailed man在Shot3和Shot5为深色马尾、黑色道服；Shot4左侧对应人物却是浅色头发、赤裸上身，外观明显不一致。 | ents: Ponytailed man:s/prompt_bound
- V2 [cross_shot/character_identity] Shot4,Shot5,Shot7 confirmed/inconsistency_confirmed/high sev=major | Sleeveless man在Shot4右侧呈束起的深色长发；Shot5与Shot7则是短浅棕发，面部也明显不同。 | ents: Sleeveless man:s/prompt_bound
- V3 [cross_shot/character_appearance] Shot2,Shot4,Shot5,Shot6,Shot8 confirmed/inconsistency_confirmed/high sev=major | Older man在Shot2、Shot6和Shot8穿橄榄卡其色有领衬衫；Shot5中可见的背部却穿浅色道服并系腰带。 | ents: Older man:s/prompt_bound
- V4 [cross_shot/setting_background] Shot1,Shot2,Shot3,Shot4,Shot5,Shot6,Shot7,Shot8 confirmed/inconsistency_confirmed/high sev=critical | 作为反复出现的训练室，Shot1、Shot2、Shot3、Shot4、Shot6及Shot8呈现的背景布置彼此不一致：入口浅灰墙与门洞、木质墙面、镜墙、群像中的酒红地面和旗帜布局，以及蓝白墙面等不能统一为同一可辨认场景。 | ents: Martial arts training room:s/prompt_bound | REV: 将笼统的背景差异具体化，并仅列出候选证据涉及的代表性镜头；不同机位本身可改变可见背景，但这些画面呈现的墙面材料、配色与整体布置差异并非简单换角度。

## runs/main_pre_element_gate/run_b/p069_wan21
- L1 [v_l/interaction] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中男子前进时没有将枪举在脸前：画面先显示他未持枪，随后枪出现在胸前，而非脸前。 | ents: Red-and-black jacket man:s, Angular firearm:s
- L2 [v_l/presence_count] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3男子头顶没有出现文字要求的下垂黄色缆线；画面上方未见缆线。 | ents: Corridor cables:s
- L3 [v_l/attribute] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3男子旁的墙面呈绿色砌块墙，未见要求的裸露砖面，不符合“green-and-bare brick wall”的描述。 | ents: Industrial corridor:s, Corridor brick walls:s
- L4.1 [v_l/attribute] Shot2 confirmed/requirement_violated/medium sev=minor | Shot2长外套人物的外套看起来为灰色而非要求的灰棕色。 | ents: Long-coat adult:s | split
- L4.2 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=minor | Shot4长外套人物的外套呈橄榄绿／灰绿色，而非要求的灰棕色。 | ents: Long-coat adult:s | split
- L5.1 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=major | Shot4中两名扭打者没有按要求跌到平台以下；画面仍显示他们在平台／平台下方入口处活动。 | ents: Red-suited masked adult:s, Long-coat adult:s, Green-brick stairwell:s, Diagonal metal handrail:s | split
- L5.2 [v_l/spatial_orientation] Shot4 confirmed/requirement_violated/high sev=major | Shot4结束时没有呈现两名成人在狭窄绿砖楼梯井旁金属扶手处缠抱在一起的画面；末帧两人仍在平台入口处跪伏。 | ents: Red-suited masked adult:s, Long-coat adult:s, Green-brick stairwell:s, Diagonal metal handrail:s | split
- V1 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一红黑夹克男子在Shot1第5帧穿红黑菱格纹夹克，而Shot3第5帧夹克呈红黑横向条纹，图案不一致。 | ents: Red-and-black jacket man:s/prompt_bound
- V2 [cross_shot/object_identity] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=major | 同一男子在Shot1第5帧持有粗大、灰黑色且带纹理的枪械；Shot3第5帧的枪械则为银灰色、细长枪管，并带有醒目的黄色挂带，外形与配件不一致。 | ents: Angular firearm:s/prompt_bound | REV: 明确为两帧中枪械的整体外形及配件差异，避免把不同部位混为单一颜色差异。
- V3 [cross_shot/setting_background] Shot1,Shot3 confirmed/inconsistency_confirmed/medium sev=major | Shot1第5帧的走廊背景为剥落绿漆的红砖墙，楼梯在后方，右侧可见绿色门；Shot3第5帧则呈现绿色砌块墙和楼梯，背景墙面材质与布局不同。 | ents: Industrial corridor:s/prompt_bound
- V4 [cross_shot/character_appearance] Shot2,Shot4 rejected/consistent_in_frames/medium sev=none | Shot2第5帧的矮身深色人物穿深棕色长外套和棕色裤子；Shot4第0帧对应人物也可见深色长外套与棕色裤装，未能确认候选所称的服饰不一致。 | ents: Short dark-clothed figure:s/prompt_bound | REV: 更正候选对Shot4服装不同的判断：可见服装总体与Shot2相符，细节不足以支持明显差异。
- V5 [cross_shot/character_appearance] Shot2,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一面罩人物在Shot2第5帧穿红黑长款服装；Shot4第0帧则穿红色与蓝黑色拼接的服装，配色和款式明显不同。 | ents: Red-suited masked adult:s/prompt_bound
- V6 [cross_shot/character_appearance] Shot2,Shot4 confirmed/inconsistency_confirmed/medium sev=major | Shot2第5帧的长外套人物穿灰色外套、暗红色裤子，头发呈棕色直发或微波；Shot4第0帧对应人物穿橄榄绿色外套、深色裤子并有卷曲头发。 | ents: Long-coat adult:s/prompt_bound

## runs/smoke/p002_wan21
- L1 [v_l/presence_count] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3中，要求“the blurred dark shape stays at the right foreground edge”，但画面右侧前景未见该深色形状，违反该要求。 | ents: Dark foreground shape:s
- L2 [v_l/action_state] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3中，要求男子“glances toward screen left”，但所引第2帧的视线朝画面右侧，而非画面左侧。 | ents: Bearded man:s
- L3 [v_l/setting_environment] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4中，要求房间处于“the dim warm room”，但画面呈现明亮的浅色墙面和明亮室内，未满足昏暗照明要求。 | ents: Warm room:s
- L4 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=major | Shot4中，合同要求男子穿“faded blue-gray T-shirt with small outlined chest lettering.”，但画面中他穿深色立领扣襟衬衫，而非褪色蓝灰T恤。 | ents: Bearded man:s
- V1 [cross_shot/character_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/medium sev=major | 同一男子在Shot4与Shot1–3相比，面部整体身份观感不同；Shot4面部轮廓及五官观感发生变化，不能仅以机位或光线解释。 | ents: Bearded man:s/prompt_bound | REV: 将候选所称发型轮廓差异留给独立的外观候选V2；本单元聚焦面部身份差异。
- V2 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一男子在Shot4的头发比Shot1–3短且卷曲更紧密；Shot4穿蓝灰色有领扣襟短袖衬衫，而Shot1–3穿蓝灰色圆领短袖T恤。 | ents: Bearded man:s/prompt_bound
- V3 [cross_shot/object_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一浅米色沙发在Shot1–3呈低平横向靠背，而Shot4呈高且圆弧环抱式靠背，外形不一致。 | ents: Beige sofa:s/prompt_bound

## runs/smoke2/p002_wan21
- L1 [v_l/attribute] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3中男子穿着有领、带门襟和纽扣的深蓝灰衬衫，而非合同要求的褪色蓝灰T恤；Shot3仅称其为“blue-gray shirt”，未对服装类型作出不同描述。 | ents: Bearded man:s | REV: 明确合同中的T恤要求适用于Shot3；修正为衬衫类型与T恤不符，而非颜色不符。
- L2 [v_l/presence_count] Shot3 confirmed/requirement_violated/high sev=moderate | Shot3中画面右侧前景边缘没有可见的暗色虚焦形状；可见区域为浅色墙面，未满足该形状须停留在右侧前景边缘的要求。 | ents: Dark foreground shape:s
- V1 [cross_shot/character_identity] Shot1,Shot4 confirmed/inconsistency_confirmed/high sev=major | 同一男子在Shot1与Shot4的面部轮廓及五官观感、肤色明显不同；Shot4看起来像另一名个体。 | ents: Bearded man:s/prompt_bound | REV: 明确差异比较为Shot1与Shot4，并将肤色与面部差异表述为同一核心身份不一致。
- V2 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一男子在Shot4的黑色卷发明显较短、卷曲更紧密；与Shot1–3较长、蓬松的卷发不一致。 | ents: Bearded man:s/prompt_bound
- V3 [cross_shot/setting_background] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=major | Shot1与Shot3这两个回到中景的镜头中，木门及墙面的相对布局不一致：Shot1木门位于人物后方中部、右侧有暗色前景；Shot3木门位于画面最左侧，人物后方右侧为大面积浅色墙面。 | ents: Warm room:s/prompt_bound, Wooden doorway:s/prompt_bound | REV: 补充了Shot1和Shot3可见的布局要点，并将候选描述中的“门移至最左侧”明确为画面位置差异。
- V4 [cross_shot/object_identity] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | Shot4中男子所坐的浅色座椅呈环抱人物的圆弧形高靠背；Shot1–3中可见的同一浅米色沙发为低矮、横向延伸的靠背，形态不一致。 | ents: Beige sofa:s/prompt_bound | REV: 将候选笼统的“座椅形态”明确为Shot4圆弧高靠背与Shot1–3低矮横向沙发靠背的差别。

## runs/smoke2/p047_wan21
- L1 [v_l/action_state] Shot1 rejected/requirement_satisfied/high sev=none | Shot1开头男子虽直立，但之后明显弯身并靠近门洞边的浅色墙；候选所称“未弓身贴墙”不成立。 | ents: White-clad man:s | REV: 更正候选对全段姿态的描述：后续帧出现弯身姿态。
- L2 [v_l/action_state] Shot1 confirmed/requirement_violated/high sev=major | Shot1男子没有向下落并从画面底部退出，而是向门洞内移动并在其中翻转腾空，最后消失。 | ents: White-clad man:s
- L3 [v_l/spatial_orientation] Shot1 rejected/requirement_satisfied/high sev=none | Shot1男子起初位于入口旁、靠近浅色墙；之后移向门洞内部。候选称他未保持在墙旁与入口边，但提示没有要求他在整个动作中保持该位置。 | ents: White-clad man:s, Martial arts training room:s, Poster wall:s | REV: 澄清文本描述的是起始位置，并未要求动作期间持续留在墙边。
- L4.1 [v_l/attribute] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4左侧马尾男子上身赤裸、仅穿黑裤；这与“Both men in black”及合同中黑色武术服的描述不符。 | ents: Ponytailed man:s | split | REV: 将候选笼统的外观不符具体化为左侧男子未穿黑色上衣/黑色武术服。
- L4.2 [v_l/attribute] Shot4 confirmed/requirement_violated/medium sev=moderate | Shot4左侧马尾男子的头发呈浅棕色、向后梳而非合同描述的深色头发；可见画面不足以确认是否在颈后束发。 | ents: Ponytailed man:s | split | REV: 将发色不符与服装问题分开，并仅陈述可见的浅棕发色；不把未能确认的束发细节作为独立违规。
- L5.1 [v_l/action_state] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4两名男子没有共同弯身再挺直：右侧无袖男子大体保持直立并转入动作，左侧赤膊男子则下蹲后腾跃、跨步。 | ents: Ponytailed man:s, Sleeveless man:s | split | REV: 描述按画面区分两人的动作，不再概括为单纯腾跃。
- L5.2 [v_l/action_state] Shot4 confirmed/requirement_violated/medium sev=moderate | Shot4左侧马尾男子未呈现张开双脚的动作；其主要动作是屈身腾跃并跨步。 | ents: Ponytailed man:s, Sleeveless man:s | split
- L6 [v_l/action_state] Shot5 confirmed/requirement_violated/high sev=major | Shot5左侧马尾男子大体直立，手臂垂在身侧，没有保持弯身守势或一手靠近胸口。 | ents: Ponytailed man:s
- L7 [v_l/interaction] Shot5 rejected/requirement_satisfied/high sev=none | Shot5无袖男子朝同伴侧向伸出张开的手，并在后续画面中保持伸出；候选声称手臂末段降低，与关键帧不符。 | ents: Sleeveless man:s, Ponytailed man:s | REV: 更正候选所称末段手臂降低：末帧仍可见手臂向同伴侧向伸出。
- L8.1 [v_l/action_state] Shot5 uncertain/not_verifiable/low sev=none | Shot5马尾男子在部分画面中朝向无袖同伴；不能据此认定没有短暂转看动作，候选所述持续朝向同伴也不构成与要求矛盾。 | ents: Ponytailed man:s, Sleeveless man:s, Mirror wall:s | split | REV: 更正“未见转看”：画面可见其朝向同伴，但不能证实缺少短暂转看。
- L8.2 [v_l/setting_environment] Shot5 confirmed/requirement_violated/medium sev=moderate | Shot5镜子上方的墙面未呈现明显暖色光纹；画面所见主要是均匀浅色墙面。 | ents: Ponytailed man:s, Sleeveless man:s, Mirror wall:s | split
- L9 [v_l/interaction] Shot6 confirmed/requirement_violated/high sev=major | Shot6近景前景出现赤膊男子的肩臂和躯干，并持续遮挡画面左侧；未见无袖男子的裸臂横过前景、遮住长者部分脸胸后再降下。 | ents: Sleeveless man:s, 左侧赤膊男子:s, Older man:s | REV: 按可见画面区分前景赤膊男子与文本指定的无袖男子，并概括遮挡及下降动作均未呈现。
- V1.1 [cross_shot/character_appearance] Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=major | 同一无袖男在Shot4 f0呈深色长发束起的发型，而Shot5 f2呈短浅棕发；两镜头中发型与发色不一致。 | ents: Sleeveless man:s/prompt_bound | split | REV: 将候选笼统的外观差异明确为发型与发色变化，并单独审查该属性。
- V1.2 [cross_shot/character_identity] Shot4,Shot5 confirmed/inconsistency_confirmed/high sev=major | 同一无袖男在Shot4 f0与Shot5 f2呈现明显不同的面部特征，人物面貌不一致。 | ents: Sleeveless man:s/prompt_bound | split | REV: 将候选中的“面部也明显不同”拆为独立的身份差异单元，不把发型差异作为本单元的判定依据。

## runs/main_template_v1/run_a/p002_wan21
- V1.1 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一男子在Shot1、Shot2和Shot3穿蓝灰色短袖圆领T恤，而Shot4穿深蓝灰色有领扣衫，衣服款式与领口明显不同。 | ents: Bearded man:s/prompt_bound | split | REV: 将服装差异单独成项，明确对比Shot1至Shot3与Shot4的衣服款式及领口。
- V1.2 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一男子在Shot1至Shot3呈较蓬松、较长的卷发；Shot4的卷发明显更短，两侧修剪得更短。 | ents: Bearded man:s/prompt_bound | split | REV: 将候选所述发型变化独立列出，并将对比范围明确为Shot1至Shot3与Shot4。
- V2 [cross_shot/object_identity] Shot1,Shot3,Shot4 confirmed/inconsistency_confirmed/high sev=moderate | 同一浅米色座椅在Shot1和Shot3呈横向延伸的低靠背外观，而Shot4呈包围人物的高圆弧靠背外观，靠背轮廓明显不一致。 | ents: Beige sofa:s/prompt_bound | REV: 将候选中“沙发”与“座椅”的表述统一为同一浅米色座椅，并明确对比靠背轮廓。

## runs/main_template_v1/run_a/p014_storymem

## runs/main_template_v1/run_a/p014_wan21
- L1 [v_l/attribute] Shot1 confirmed/requirement_violated/high sev=moderate | Shot1中女子的灰色冬外套没有呈现扣合的纽扣，而是以腰带系合；这与要求她穿着扣合的灰色冬外套不符。 | ents: Woman in gray coat:s
- L2 [v_l/action_state] Shot4 uncertain/not_verifiable/high sev=none | Shot4首帧中老人背对镜头，脸部不可见，因此无法判断其起始时是否低下；现有画面不足以确认或否定“脸低下”的要求。 | ents: Older man in earflap hat:s | REV: 将候选所称背影不符合低头要求修正为脸部不可见，因而无法从首帧判断脸是否低下。
- L3 [v_l/spatial_orientation] Shot4 confirmed/requirement_violated/high sev=moderate | Shot4首帧中老人背对镜头，未呈现要求的画面左侧面。 | ents: Older man in earflap hat:s
- V1 [cross_shot/character_appearance] Shot1,Shot3 confirmed/inconsistency_confirmed/high sev=moderate | 同一女子在Shot1（frame 5）穿灰色系带外套，桃色高领内搭从外套领口露出；Shot3（frame 5）则穿有黑色双排扣的灰色外套，桃色衣物围在颈部成为围巾，未见换装动作。 | ents: Woman in gray coat:s/prompt_bound | REV: 明确两处服装差异：外套款式，以及桃色衣物从高领内搭变为围巾。
- V2 [cross_shot/setting_background] Shot1,Shot2,Shot3,Shot4 uncertain/not_verifiable/low sev=none | 被标为同一庭院的Shot1、Shot2、Shot3和Shot4呈现不同建筑与背景构成：Shot1为棕灰色石质多层建筑及方窗，Shot2为浅色立面和高拱窗，Shot3可见低矮独立小楼，Shot4可见浅色建筑、黑铁栏杆及近景树干；仅凭这些画面无法确认差异是否超出同一庭院不同方向可见的建筑。 | ents: Courtyard:s/prompt_bound | REV: 将“明显不匹配、机位变化不足以解释”的定论修正为可见背景差异，并指出现有画面无法确定其是否互相矛盾。

## runs/main_template_v1/run_a/p028_wan22
FAILED

## runs/main_template_v1/run_a/p032_wan22
- L1 [v_l/attribute] Shot6 confirmed/requirement_violated/high sev=moderate | Shot6 中猫的头部和尾部可见明显黑色区域，身体大部分为白色；这与要求的“ A short-haired white cat”中猫为白色的描述不符。 | ents: White cat:s | REV: 将概括性的“猫身上有明显黑色斑块”具体说明为头部和尾部可见黑色区域，身体大部分为白色；核心颜色不符问题不变。
- V1 [cross_shot/character_appearance] Shot1,Shot2,Shot3,Shot4,Shot5,Shot6 confirmed/inconsistency_confirmed/high sev=moderate | 同一男子在Shot1–Shot5穿着较宽的深浅格纹衬衫并系深色领带；Shot6所见衬衫格纹明显更细密，形成跨镜头服装外观差异。 | ents: 格子衫男子:s/prompt_bound | REV: 将描述限定为可直接比较的格纹疏密差异；Shot6画面中仍能看到深色领带，因此删除了“无领带”的错误描述。
- V2 [cross_shot/object_identity] Shot3,Shot4 rejected/normal_change/medium sev=none | Shot3中烤箱正面可见浅色外框及黑色玻璃门；Shot4中画面左侧主要呈现该设备的黑色侧面。 | ents: 嵌入式烤箱:s/prompt_bound, 厨房:c/prompt_bound | REV: 将差异表述为正面与侧面的可见外观区别，避免把不同视角误说成设备本体外观改变。

## runs/main_template_v1/run_a/p047_storymem
FAILED

## runs/main_template_v1/run_a/p047_wan21
FAILED

## runs/main_template_v1/run_b/p002_wan21
FAILED


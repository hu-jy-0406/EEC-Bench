# Unspecified branch: matching sheet (generated)

## dev

### priority_013__cinetrans
- TARGET 013-A2 [cross_shot] green glass vase-like object above the red chair (Shot1/Shot3; possibly the contract green glass lamp or palm leaves) :: Solid green cylinder in Shot1, only a faint translucent ghost at the same spot in Shot3, replaced at that spot by a green leather chair in Shot2 and a bright green glass shade on a stand in Shot4.
- inventory objects - (new -), suspects 2, real 0, USD 0.000869
- S1 [cross_shot] Shot1:ge0001 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (四个镜头中画面右侧都能看到承托着白色布料堆的棕色桌面，桌子的位置和外观保持一致。虽然其他镜头的库存未列出该物体，但图像显示它并未缺失。)
- S2 [cross_shot] Shot1:ge0002 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (四个镜头右侧棕色桌面上都能看到相同的白色折叠布料堆，位置和外观一致。)

### priority_025__storymem
- TARGET 025-A1 [cross_shot] wall light switch :: A white light switch on the flat wall left of the Younger man is visible throughout Shot2, but in Shot4, which the prompt says returns to the same alternate view, that side is an arched niche and no switch appears.
- TARGET 025-A2 [cross_shot] cut-glass teapot, blue ornament and red-framed botanical print (with a row of arched niches holding bottles) :: Shot4's returning alternate view shows a niche at left with a cut-glass teapot and a blue ornament below a red-framed botanical print, plus a corridor of niches with bottles at right, none of which exists in Shot2's view of the same spot (flat wall with one dark-framed picture and a single alcove with three small figurines).
- inventory objects - (new -), suspects 8, real 1, USD 0.012946
- S1 [cross_shot] Shot1:Shot1/o1 vs Shot2=ge0001, Shot3=Shot3/o1, Shot4=ge0001 -> **not_real** [] (各镜头都能看到顶部的天花灯；正面镜头只露出灯具的一小部分，另一个机位则从不同角度显露更多灯罩。画面中的位置和形状差异可由机位与裁切解释，不能确认存在不一致。)
- S2 [cross_shot] Shot1:Shot1/o2 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (Shot1右侧门边可见窄长深色墙面装置；同为正面视角的Shot3右侧门边也能看到相同装置。Shot2和Shot4为另一机位，未清楚呈现该装置所在位置，不能据此判定其缺失。)
- S3 [cross_shot] Shot2:ge0001 vs Shot1=Shot1/o1, Shot3=Shot3/o1, Shot4=ge0001 -> **unclear** [] (Shot2顶部可见矩形灯，Shot4顶部右侧可见圆形灯，但Shot4是不同视角，画面中还可能有其他顶灯，无法确定它们是否为同一盏灯。现有帧不足以判定为物体形状不一致。)
- S4 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot3=-, Shot4=- -> **unclear** [] (Shot2中可见左墙低处、画框左下方有白色开关面板，但其他镜头采用不同视角或取景，未能清楚呈现这一墙面位置，无法确认开关是否缺失。)
- S5 [cross_shot] Shot3:Shot3/o1 vs Shot1=Shot1/o1, Shot2=ge0001, Shot4=ge0001 -> **unclear** [] (Shot1和Shot3的灯具在画面顶缘只露出很小一部分，难以确认其形状与中心结构。Shot2和Shot4所见灯具外形不同，但裁切与视角差异使其是否为同一盏灯无法判定。)
- S6 [cross_shot] Shot4:ge0001 vs Shot1=Shot1/o1, Shot2=ge0001, Shot3=Shot3/o1 -> **real** ['Shot2', 'Shot4'] (同一走廊顶部的灯具在不同镜头中呈现出明显不同的外形：Shot2中是长方形灯罩，Shot4中则是圆形玻璃灯罩。画面都能看到灯具，差异不像是单纯裁切造成的。)
- S7 [cross_shot] Shot4:ge0002 vs Shot1=-, Shot2=-, Shot3=- -> **unclear** [] (Shot1和Shot3主要展示走廊另一侧，无法确认镜子所在位置；Shot2与Shot4的侧向视角及遮挡也不同，画面中看不清是否是同一块反光面板。)
- S8 [cross_shot] Shot4:ge0003 vs Shot1=-, Shot2=-, Shot3=- -> **not_real** [] (Shot4左侧墙上的深红棕色矩形画框，在Shot2左侧墙面也能看到相似的画框；Shot1和Shot3采用不同的正面取景，未呈现该处墙面，因此不构成缺失。)
- U V1 <- V1 **rejected** [cross_shot/object_identity] ge0001:unspecified :: 走廊顶部可见的灯具在Shot2画面中呈长方形，在Shot4画面中呈圆形玻璃罩状，外形不一致。

### priority_036__holocine
- TARGET 036-A2 [cross_shot] plants on the bay-window sill :: A row of small green plants sits along the bottom of the bay window in every Shot4 frame, but the same window's sill is bare in Shot1.
- TARGET 036-A3 [cross_shot] dark canopy over the garage opening :: In Shot4 a dark grey porch canopy projects over the garage opening and brick pillar and covers the bay window's top-left corner; in Shot1 there is no canopy there, only the white garage-door housing with a lantern.
- inventory objects - (new -), suspects 10, real 3, USD 0.01135
- S1 [within_shot] Shot1:Shot1/o3 vs  -> **real** ['Shot1'] (画面右下方的前院地面在前两帧清晰可见且没有该物体；到末帧，同一位置出现一个小型白色物体，未见它进入画面的过程或其他动作解释。)
- S2 [cross_shot] Shot1:ge0001 vs Shot2=-, Shot4=- -> **not_real** [] (Shot1 中车库门上方左侧可见黑色壁灯；Shot2 和 Shot4 都是无人机近景，车库门上方左侧这一位置未入镜或无法辨认，因此不能据此认定壁灯缺失。)
- S3 [cross_shot] Shot1:ge0002 vs Shot2=-, Shot4=- -> **not_real** [] (Shot1 中车库地面后方可见一辆带绿色部件的园艺推车；Shot2 和 Shot4 是无人机及房屋外墙的近景，车库及推车所在位置均未入镜，因此不能据此认定推车缺失。)
- S4 [cross_shot] Shot1:ge0003 vs Shot2=-, Shot4=- -> **real** ['Shot1', 'Shot4'] (Shot1 中，凸窗右侧的砖墙上清楚可见一扇窄竖窗；Shot4 也展示了凸窗右侧及相邻墙面，但该窗缺失，且没有遮挡或取景变化足以解释。)
- S5 [cross_shot] Shot1:Shot1/o1 vs Shot2=Shot2/o1, Shot4=Shot4/o1 -> **not_real** [] (Shot1 中铁栏杆外可见无叶灌木，Shot2 的虚化背景也能看到枝状植被。Shot4 的绿色植物位于窗台，和栏杆外的灌木不是同一处；目标灌木所在区域在该近景中基本不在画面内，不能据此判为不一致。)
- S6 [cross_shot] Shot1:Shot1/o2 vs Shot2=-, Shot4=- -> **not_real** [] (Shot4 在窗下、墙脚位置可见一簇低矮绿植，与 Shot1 所示靠近车库转角的墙脚绿植区域相符。Shot2 是无人机近景，未拍到该处，不能据其清单未列出就判定绿植缺失。)
- S7 [cross_shot] Shot1:Shot1/o3 vs Shot2=-, Shot4=- -> **unclear** [] (Shot1右下角可见一个被画面边缘截断的小白色物体；Shot2和Shot4是无人机近景，没有清楚呈现它所在的前院位置，无法判断该物体是否缺失。)
- S8 [cross_shot] Shot2:Shot2/o1 vs Shot1=Shot1/o1, Shot4=Shot4/o2 -> **not_real** [] (Shot2 中无人机后方的虚化背景可见细密的裸枝轮廓；Shot1 和 Shot4 的远景也有栏杆后的无叶枝木，画面景别与取景不同并不构成矛盾。)
- S9 [cross_shot] Shot4:Shot4/o1 vs Shot1=Shot1/o1, Shot2=- -> **real** ['Shot4', 'Shot1'] (Shot4 的飘窗窗台上清楚可见一排低矮深绿色植物；同一窗台在 Shot1 中可见的部分呈空白，未见这些植物，画面中没有明显原因解释这一差异。)
- S10 [cross_shot] Shot4:Shot4/o2 vs Shot1=-, Shot2=Shot2/o1 -> **not_real** [] (Shot1中铁栏杆后方可见枝叶稀疏的树木；Shot4同一栏杆后方也有模糊的裸枝背景，与树木存在相符。)
- U V1 <- V1 **uncertain** [within_shot/presence_instability] n1:unspecified :: Shot1画面右下缘的地面上，帧0和帧1未见小型白色直立物体；到帧5，该处出现一个白色物体，顶部较暗并带有细小突起，帧间没有显示它进入或被放置的过程。
- U V2 <- V2 **rejected** [cross_shot/setting_background] ge0003:unspecified :: 同一砖房的窗户布局不一致：Shot1帧3中，凸窗右侧的砖墙上有一扇带深色窗格和白色窗框的窄竖窗；Shot4帧2展示凸窗右侧邻近砖墙区域时，没有看到这扇窄竖窗。
- U V3 <- V3 **confirmed** [cross_shot/setting_background] n2:unspecified n3:unspecified :: 砖房凸窗底部窗台上的植物状装饰不一致：Shot4帧3的窗台上可见一簇低矮的深绿色植物；Shot1帧3所见的窗台部分没有这簇植物，呈空置状态。

### priority_047__storymem
- TARGET 047-A1 [cross_shot] white notice paper on the poster wall :: An unprompted white notice sheet (small photo at its top) hangs on the poster wall left of and below the switch plates in Shot2 f0-f1 and Shot6 f5 at the same offset from the switches, but in Shot1 f1-f5 that spot is bare wall although it is in view.
- TARGET 047-A2 [cross_shot] rear-wall shelves, two white banners and red emblem :: Behind the two men in Shot5 the rear of the room shows wall shelves with items, two white vertical banners with a red emblem between them and posters, while Shot4, looking the same way over the Older man's back, shows a plain rear wall with only a ladder and flag and none of these items.
- inventory objects - (new -), suspects 11, real 2, USD 0.016078
- S1 [within_shot] Shot2:Shot2/o1 vs  -> **not_real** [] (白色纸质告示在第0帧清楚可见，第1帧仍可见其局部；后续帧中该位置被男子身体遮挡，符合描述，没有显示告示消失。)
- S2 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **real** ['Shot1', 'Shot2'] (Shot1中，浅色墙上的细黑色竖向电线管连接到开关面板；Shot2在同一海报墙上仍能看到对应开关及其上方墙面，却没有电线管，画面中也没有遮挡或其他解释。)
- S3 [cross_shot] Shot1:Shot1/o2 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **unclear** [] (Shot1中门内黄色墙面左侧可见一个小型米色矩形装置，但其他镜头主要拍摄训练室内景或另一面墙，未能清楚呈现该装置所在位置。因此无法判断它是否在其他镜头中缺失。)
- S4 [cross_shot] Shot1:Shot1/o3 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **unclear** [] (Shot1中门内黄色墙面上可见一个小型暗红色圆形装置，但其他附带画面没有清楚呈现这块墙面及其对应位置，无法确认它是否缺失。)
- S5 [cross_shot] Shot1:Shot1/o4 vs Shot2=-, Shot3=-, Shot4=Shot4/o1, Shot5=Shot5/o3 -> **not_real** [] (Shot1 的门口上方可见一块亮色矩形顶灯；Shot4 的宽景中有成排顶灯，Shot5 也能在镜面中看到顶灯反射。Shot2、Shot3 是墙面近景，未拍到天花板，因此不构成缺失。)
- S6 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot3=-, Shot4=-, Shot5=- -> **real** ['Shot2', 'Shot1'] (Shot2 的人物肩后可见一小块竖向白色告示；Shot1 展示了有相似海报、开关和条纹光影的墙面，告示所在区域清晰可见但没有这张纸，且没有遮挡或动作解释其缺失。)
- S7 [cross_shot] Shot4:Shot4/o1 vs Shot2=-, Shot3=-, Shot5=Shot5/o3, Shot6=- -> **not_real** [] (Shot4清楚可见训练室天花板上的矩形灯板，Shot5也在镜面背景中显示相同的顶灯。Shot2、Shot3和Shot6是人物近景，画面没有覆盖天花板，因此不能据此认定灯具缺失。)
- S8 [cross_shot] Shot4:Shot4/o2 vs Shot2=-, Shot3=-, Shot5=-, Shot6=- -> **unclear** [] (Shot4中目标位置大部分被人物遮挡，无法清楚确认橙红色训练垫；其他镜头是人物近景或不同机位，未显示该位置，因此无法判断它是否缺失。)
- S9 [cross_shot] Shot5:Shot5/o1 vs Shot3=-, Shot4=-, Shot6=-, Shot7=- -> **unclear** [] (Shot5中镜面后方能看到浅色开放式搁架；其他近景主要拍摄浅色墙面，未显示同一处背景。Shot4虽是较宽的房间视角，但后墙细节太远，无法确认搁架是否缺失。)
- S10 [cross_shot] Shot5:Shot5/o2 vs Shot3=-, Shot4=-, Shot6=-, Shot7=- -> **not_real** [] (Shot3、Shot6和Shot7的浅色墙面上方都能看到被画面边缘裁切的深色矩形标牌，与Shot5所列墙面图片/告示相符。各镜头取景远近不同，不构成物件缺失或变化。)
- S11 [cross_shot] Shot5:Shot5/o3 vs Shot3=-, Shot4=Shot4/o1, Shot6=-, Shot7=- -> **not_real** [] (Shot5和Shot4均可见训练室顶部的矩形灯板；Shot3、Shot6和Shot7的近景中，背景墙上也有与顶灯相符的明亮长条光影。镜头取景和视角不同，不构成灯具缺失或不一致。)
- U V1 <- V1 **rejected** [cross_shot/setting_background] n1:unspecified :: 训练室浅色海报墙上的细黑色竖向电线管在Shot1帧3中从画面上方延伸至开关面板；Shot2帧2中可见开关面板及其上方墙面，但该电线管缺失。
- U V2 <- V2 **rejected** [cross_shot/setting_background] n2:unspecified :: 训练室浅色海报墙上的小型竖向白纸告示在Shot2帧1中可见，位于老人肩部后方的较低墙面处；Shot1帧2展示了相应墙面区域，但未见该告示。

### priority_055__wan21
- TARGET 055-A1 [cross_shot] background furnishings behind the woman (upper wooden wall cabinet, countertop items, dark box, gold-object shelf) :: The unprompted furnishings behind the woman are not carried over between her two reverse views: Shot2 shows an upper wooden wall cabinet above the counter at right with bottles/jars on the counter, while Shot4 (same interior, counter again behind her at right) has no cabinet but an open shelf of gold objects and a dark box with a glowing gold item on the counter.
- inventory objects - (new -), suspects 7, real 3, USD 0.012779
- S1 [cross_shot] Shot2:ge0001 vs Shot1=-, Shot3=-, Shot4=- -> **not_real** [] (Shot2中可见墙上的暖光壁灯；Shot1和Shot3取景集中在床与人物，Shot4呈现柜台和吊灯的另一背景视角，均未清楚展示壁灯所在位置，不能据此认定其缺失。)
- S2 [cross_shot] Shot2:ge0002 vs Shot1=-, Shot3=-, Shot4=- -> **not_real** [] (Shot2 右上方可见一只红棕色壁柜；Shot1、Shot3是床铺方向的镜头，Shot4的背景取景方向和构图不同，均未清楚呈现壁柜所在位置。因此不能据此认定壁柜消失或发生变化。)
- S3 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot3=-, Shot4=- -> **real** ['Shot2', 'Shot4'] (Shot2与Shot4都呈现同一室内的柜台区域，但Shot2柜台上有一簇彩色瓶罐和盒状容器，Shot4可见的柜台上却没有这簇物品。画面没有显示遮挡或物品被移走的动作来解释差异。)
- S4 [cross_shot] Shot4:ge0003 vs Shot1=-, Shot2=-, Shot3=- -> **not_real** [] (Shot4中可见多盏暖白色吊灯；Shot2也清楚显示一盏相似的暖白色吊灯，符合该背景物件，画面取景不同可解释其他吊灯未入镜。Shot1和Shot3未显示相关背景区域，不能据此认定物件缺失。)
- S5 [cross_shot] Shot4:ge0004 vs Shot1=-, Shot2=-, Shot3=- -> **not_real** [] (Shot4中吧台上方可见多盏吊灯；Shot2的反向视角中也能看到一盏外形和暖白色调相符的吊灯，可对应同一处灯具。Shot1和Shot3主要取景在床与人物，未显示该灯所在区域，不能据此判定缺失。)
- S6 [cross_shot] Shot4:ge0005 vs Shot1=-, Shot2=-, Shot3=- -> **real** ['Shot4', 'Shot2'] (Shot4中女子身后可见宽圆罩的吊灯；同一房间的Shot2对应背景位置只见一盏小型壁灯式灯具，形状和安装方式不同，画面也没有解释这种变化。)
- S7 [cross_shot] Shot4:Shot4/o1 vs Shot1=-, Shot2=-, Shot3=- -> **real** ['Shot4', 'Shot2'] (Shot4 的柜台后方右侧可见一个近黑色、竖直的矩形物体；Shot2 也展示了同一后方柜台区域，但看不到对应物体，柜台上的杂物没有明显遮住该位置。)
- U V1 <- V1 **rejected** [cross_shot/object_identity] n1:unspecified :: Shot2中，右后方柜台上可见一簇白色、绿色、红色及深色的小瓶罐和盒状容器；Shot4中可见的后方柜台区域没有出现这簇容器。
- U V2 <- V2 **confirmed** [cross_shot/object_identity] ge0005:unspecified :: Shot2女子身后墙面上方可见一盏小型壁灯式灯具，带深色装饰灯座；Shot4背景上方则可见宽圆罩的吊灯，灯具类型和外形不同。
- U V3 <- V3 **rejected** [cross_shot/object_identity] n2:unspecified :: Shot4右后方柜台上方可见一个近黑色、顶部略圆的竖直小矩形物体；Shot2对应的右后方柜台及其周围区域没有看到该物体。

### priority_078__wan22
- TARGET 078-A1 [cross_shot] TV stand / cabinet under the television :: The same living-room corner (TV beneath the wall clock, hallway at right) has the TV standing on a white cabinet with drawers in Shot2 but on a dark wood/black stand flanked by black set-top boxes in Shot5.
- inventory objects - (new -), suspects 6, real 3, USD 0.010928
- S1 [cross_shot] Shot2:ge0003 vs Shot4=-, Shot5=ge0003 -> **real** ['Shot2', 'Shot5'] (Shot2中电视下方可见白色电视柜，而Shot5同一位置呈现深色柜体，颜色明显不同。Shot4的镜头未拍到电视区域，因此不构成对比证据。)
- S2 [cross_shot] Shot2:Shot2/o1 vs Shot4=-, Shot5=- -> **unclear** [] (Shot4的取景转向窗户和百叶帘，Shot2中开关所在的墙面没有入镜。Shot5虽能看到走廊入口，但相邻墙面被人物遮挡，无法确认开关是否缺失。)
- S3 [cross_shot] Shot5:ge0001 vs Shot2=-, Shot4=- -> **unclear** [] (Shot5 中走廊墙面可见疑似窄长深色装饰，但 Shot2 的走廊区域较暗且视角受限，无法确认对应墙面是否清楚可见；Shot4 的镜头朝向窗户一侧，未呈现该走廊位置。因此这些画面不足以判断装饰物是否缺失。)
- S4 [cross_shot] Shot5:ge0003 vs Shot2=ge0003, Shot4=- -> **real** ['Shot2', 'Shot5'] (Shot2与Shot5都能看到电视下方的柜体，且取景均展示了该处。Shot2中的电视柜是白色，Shot5中的则呈深色，画面没有解释这一颜色差异。)
- S5 [cross_shot] Shot5:ge0004 vs Shot2=-, Shot4=- -> **unclear** [] (Shot5中能看到电视柜附近的深色小物件，但Shot2的画面把电视左侧及柜子左端裁在画面边缘，无法确认该物件应在的位置是否完整可见。Shot4展示的是房间另一侧，电视柜不在画面内，因此这些帧不足以判定物件缺失。)
- S6 [cross_shot] Shot5:Shot5/o1 vs Shot2=-, Shot4=- -> **real** ['Shot5', 'Shot2'] (Shot5中电视右侧的电视柜上清楚可见一个黑色小盒子；Shot2也展示了同一电视及其右侧柜面，但可见区域没有这个盒子，且没有明显遮挡或动作能解释其缺失。)
- U V1+V2 <- V1,V2 **confirmed** [cross_shot/object_identity] ge0003:unspecified :: 电视下方的电视柜在Shot2中呈白色，在Shot5中可见部分呈深色。
- U V3 <- V3 **rejected** [cross_shot/object_identity] n1:unspecified :: 电视柜面上的小型黑色矩形盒子在Shot5的电视右侧清晰可见；Shot2中电视右侧对应的可见柜面区域没有看到该盒子。

### priority_120__storymem
- TARGET 120-A1 [within_shot] baton / thin stick held by the Suited man :: The thin wooden stick (black-tipped baton or pencil) held in the Suited man's right hand at the right edge in f0 stays hanging at the same spot in f1-f2 (and again in f4) after he has turned and lowered his arms, with no hand or visible support holding it.
- inventory objects - (new -), suspects 8, real 1, USD 0.010349
- S1 [within_shot] Shot3:Shot3/o3 vs  -> **not_real** [] (第3、4帧中男子伸出的手臂遮挡了画面右侧短杆所在区域，因此短杆看似消失可由遮挡解释。)
- S2 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=Shot3/o1, Shot4=- -> **not_real** [] (Shot1与Shot3都能看到背景高处的绿色发光标牌，Shot3只是视角更近，标牌的浅色部分更清楚。Shot2背景严重虚化且景别较近，Shot4没有展示标牌所在位置，未见足以确认的缺失或矛盾。)
- S3 [cross_shot] Shot1:Shot1/o2 vs Shot2=-, Shot3=Shot3/o1, Shot4=- -> **not_real** [] (Shot1右侧后方可见小型绿色发光标牌，Shot3椅列上方也可见绿色白色发光标牌，位置与外观相符。Shot2和Shot4是近景，未呈现足以判断该标牌所在位置的背景，不能据此认定标牌缺失。)
- S4 [cross_shot] Shot1:Shot1/o3 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (Shot1中可见后方上部的红色弧形栏杆。Shot2至Shot4均为人物近景或中景，栏杆所在的后方上部区域未入画，因此不能据此认定栏杆缺失。)
- S5 [cross_shot] Shot3:Shot3/o1 vs Shot1=Shot1/o1/Shot1/o2, Shot2=-, Shot4=- -> **not_real** [] (Shot1 和 Shot3 的背景高处都能看到发光的绿色/浅色矩形标志，与同一场地中的标志相符。Shot2 与 Shot4 是近景，相关墙面没有清晰入镜，不能据此判断标志缺失。)
- S6 [cross_shot] Shot3:Shot3/o2 vs Shot1=-, Shot2=-, Shot4=- -> **not_real** [] (Shot3 后方可见一条横向深红棕色栏杆，Shot2 背景中也能看到相符的横向棕色条带。Shot1 是俯拍广角，背景构图与视角不同，未能证明该栏杆缺失；其余近景也没有清楚展示该处。)
- S7 [cross_shot] Shot3:Shot3/o3 vs Shot1=-, Shot2=-, Shot4=- -> **real** ['Shot3', 'Shot1'] (Shot3中右侧椅子上方、后方栏杆前清楚伸入一根浅棕色细杆；Shot1以广角展示同一乐团空间及椅列，但对应区域没有看到这根杆，且未见能解释其缺失的遮挡或动作。)
- S8 [cross_shot] Shot4:Shot4/o1 vs Shot1=-, Shot2=-, Shot3=- -> **not_real** [] (Shot4左侧的黑色立杆状物与Shot3左侧可见的带横向灯具的谱架相符；其他画面取景不同或范围较窄，未显示出可确认的缺失。)
- U V1 <- V1 **rejected** [cross_shot/object_identity] n1:unspecified :: 同一管弦乐空间中，Shot3画面右缘可见一根浅棕色、细直的杆状物横向伸入画面；Shot1的广角画面展示了该空间及椅列、后方区域，但未见这根杆状物。

### priority_126__cinetrans
- TARGET 126-A1 [within_shot] wooden deck-chair frame at screen left (Shot1) :: The lounger at screen left looks like a chair with teal/red fabric in f0 but a bare pale wooden frame with a loose white cloth in f1-f5, and the frame's shape keeps shifting between frames.
- TARGET 126-A2 [cross_shot] small round side table beside the striped chair :: Shot2 shows a solid brown wooden round table beside the striped chair; in Shot4, with the same chair and umbrella seen from the same direction, the table is a gray, semi-transparent ghost-like surface.
- TARGET 126-A3 [cross_shot] blue-and-white towel/bag on the striped chair seat :: A blue-and-white patterned item lies on the striped chair's seat in every Shot2 frame but is gone in Shot4, where the same chair is in view and nobody touched it.
- inventory objects - (new -), suspects 0, real 0, USD 0.0

**dev totals**: {"videos": 8, "suspects": 52, "real": 13, "objects": 0, "new_objects": 0, "units": 12, "confirmed": 3, "confirmed_unspecified": 3}

## val

### priority_080__cinetrans
- inventory objects - (new -), suspects 1, real 1, USD 0.005151
- S1 [cross_shot] Shot3:Shot3/o1 vs Shot1=-, Shot2=-, Shot4=- -> **real** ['Shot3', 'Shot2'] (Shot3 的厨房背景中，左侧低处的墙面插座清晰可见；Shot2 的相同位置附近有无遮挡的 backsplash，但没有插座。该处并未被遮挡，也不是明显的取景差异所致。)
- U V1 <- V1 **rejected** [cross_shot/setting_background] n1:unspecified :: 厨房橱柜下方、画面左侧低处的墙面，在Shot3（如frame 3）可见一块浅色小矩形插座面板；Shot2（如frame 2）对应的可见墙面没有这块面板。

### priority_170__cinetrans
- inventory objects - (new -), suspects 5, real 1, USD 0.007579
- S1 [within_shot] Shot4:ge0006 vs  -> **not_real** [] (第2帧可见一副深色眼镜在男子头部附近；第5帧他的手仍在眼镜两侧，符合他正在摆弄眼镜的动作，没有无法解释的变化。)
- S2 [cross_shot] Shot3:ge0003 vs Shot4=- -> **not_real** [] (Shot3右侧扶手上可见浅灰米色、带横向纹理的圆柱状物；Shot4右侧扶手边缘也能看到相似的浅色横纹物体，未见足以确认的不一致。)
- S3 [cross_shot] Shot3:ge0004 vs Shot4=- -> **not_real** [] (Shot3 和 Shot4 中蓝眼镜男子下方及两侧都能看到同一把黄色/芥末色的软垫座椅，宽圆扶手和高靠背也相符。虽然 Shot4 的库存未列出该物件，画面并未显示它缺失。)
- S4 [cross_shot] Shot3:ge0005 vs Shot4=- -> **real** ['Shot3', 'Shot4'] (Shot3 中胡子男人下方及右侧可见芥末黄色扶手椅；Shot4 同一座位处清楚可见红色扶手椅，椅子的颜色和外观不一致，画面中没有解释这种变化的因素。)
- S5 [cross_shot] Shot4:ge0006 vs Shot3=- -> **unclear** [] (Shot3 中男子头部清楚可见，没有明显的眼镜；Shot4 中他双手挡在头部两侧，也看不清是否正拿着眼镜。现有画面无法确认 Shot4 所列的眼镜是否实际出现，因此不足以判定为跨镜头不一致。)
- U V1 <- V1 **rejected** [cross_shot/object_identity] ge0005:unspecified :: Shot3画面右侧、胡子男人所坐的座椅在可见处呈芥末黄色；Shot4画面右侧胡子男人所坐的扶手椅呈红色，座椅颜色及外观不同。

### priority_046__cinetrans
- inventory objects - (new -), suspects 7, real 1, USD 0.007917
- S1 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (四个画面中，人物后方的柜体下方都能看到同一条横向的深灰色台面。其他镜头虽未在清单中列出该物体，但画面显示它持续存在，没有可见的不一致。)
- S2 [cross_shot] Shot1:Shot1/o2 vs Shot2=Shot2/o2, Shot3=Shot3/o1, Shot4=Shot4/o1 -> **not_real** [] (四个画面中，后方柜台最右侧都能看到同一个小型圆润容器，颜色偏灰米色且顶部较暗。其大小和位置一致，没有明显的物体差异。)
- S3 [cross_shot] Shot1:Shot1/o3 vs Shot2=Shot2/o1, Shot3=-, Shot4=- -> **not_real** [] (四个画面右侧背景的台面上方都能看到同一处小型浅色物体，位置与外观保持一致。Shot3 和 Shot4 的清单未列出该物体，但画面并未显示它缺失。)
- S4 [cross_shot] Shot2:Shot2/o1 vs Shot1=Shot1/o3, Shot3=-, Shot4=- -> **not_real** [] (Shot1、Shot2及Shot4的背景右侧都能看到同一处小型浅色方形物件；Shot3虽未列出该物件，画面中该处也仍可见，因此没有显示出缺失或变化。)
- S5 [cross_shot] Shot2:Shot2/o2 vs Shot1=Shot1/o2, Shot3=Shot3/o1, Shot4=Shot4/o1 -> **real** ['Shot2', 'Shot3'] (Shot2 右侧柜台下方可见一个浅灰褐色小圆罐；Shot3 同一位置清楚可见，但小罐消失，且没有遮挡或动作能解释这一变化。)
- S6 [cross_shot] Shot3:Shot3/o1 vs Shot1=Shot1/o2, Shot2=Shot2/o2, Shot4=Shot4/o1 -> **not_real** [] (四个镜头中，柜子下方后侧台面的最右端都能看到同一个小型圆钝容器，颜色和轮廓基本一致。)
- S7 [cross_shot] Shot4:Shot4/o1 vs Shot1=Shot1/o2, Shot2=Shot2/o2, Shot3=Shot3/o1 -> **not_real** [] (四个镜头中，柜台最右侧、橱柜下方都能看到同一个小型灰米色圆罐，顶部较暗；没有明显的缺失或外观变化。)
- U V1 <- V1 **rejected** [cross_shot/object_identity] n1:unspecified n2:unspecified :: 厨房后方右侧柜台、墙柜下方的小圆罐在 Shot2 frame 3 中清晰可见；Shot3 frame 3 的对应右侧柜台区域中未见该罐。

### priority_149__cinetrans
- TARGET 149-A1 [cross_shot, clear] chair back at the bottom-left corner :: With the same camera view and in the same spot, the chair back is a gray/silver perforated mesh back throughout Shot1 but a dark brown leather back in Shot2, Shot3 and Shot4; no chair is named in Shots 1-3 (it might be read as the 'dark seating' named only for Shot4).
- TARGET 149-A2 [within_shot, likely] chair back at the bottom-left corner :: In Shot1 f0 the object in that spot looks like a smooth translucent bluish glass, and from f1 on it is a gray perforated chair back (f0 is a degraded first frame overall).
- inventory objects - (new -), suspects 5, real 0, USD 0.003186
- S1 [cross_shot] Shot1:ge0001 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (其他镜头的取景较紧，杯子所在的画面左下缘被裁切或受椅子、人物遮挡，不能据此判断杯子缺失。Shot3左下方还能看到一个小型半透明容器，未见足以确认其与Shot1中的玻璃杯不一致的证据。)
- S2 [cross_shot] Shot1:ge0002 vs Shot2=-, Shot3=Shot3/o1, Shot4=- -> **not_real** [] (各镜头画面左下方都能看到部分深色椅背；Shot2 中椅背虽被裁切且不显眼，Shot4 中也清楚露出，因此没有证据表明椅子缺失或发生变化。)
- S3 [cross_shot] Shot3:ge0003 vs Shot1=-, Shot2=-, Shot4=- -> **unclear** [] (Shot3中能看到桌边有一只蓝白色小瓶，但其他镜头的对应位置被人物遮挡、裁切或过暗，无法确认瓶子是否缺失。)
- S4 [cross_shot] Shot3:ge0004 vs Shot1=-, Shot2=-, Shot4=- -> **unclear** [] (Shot3中可见桌上的小瓶，但其他镜头的取景没有清楚展示该桌面位置，无法判断瓶子是否缺失。)
- S5 [cross_shot] Shot3:Shot3/o1 vs Shot1=ge0002, Shot2=-, Shot4=- -> **not_real** [] (Shot3 左下方的深色椅背在画面中可见；Shot1、Shot2 和 Shot4 的左下方也能看到相似的椅背。其他镜头清单未列出该物体，但画面并未显示它缺失或发生变化。)

### priority_188__holocine
- TARGET 188-A1 [cross_shot, likely] brown leather bag or jacket beside the seated man :: An unprompted brown leather bag or jacket leans against the wall just behind the seated man, right of the dark case, in Shot4 and Shot7, but is not visible in Shot6, which shows the same case and papers (the man is also missing there, and the standing hooded person may partly block the spot).
- inventory objects - (new -), suspects 3, real 0, USD 0.001631
- S1 [within_shot] Shot8:ge0001 vs  -> **not_real** [] (第3帧苹果下方露出一小块深色、带蓝色反光的积水；第5帧苹果已被拿走后，该积水仍留在原处，符合描述。)
- S2 [cross_shot] Shot8:ge0001 vs Shot4=-, Shot5=-, Shot6=-, Shot7=- -> **not_real** [] (Shot8 中苹果被提起后，原先被遮住的位置露出一小块深色反光区域；Shot5、Shot6 和 Shot7 的苹果仍在地面上，遮挡了该处，远景也不足以辨清小物体。因此没有证据表明水洼在其他镜头中缺失。)
- S3 [cross_shot] Shot8:Shot8/o1 vs Shot4=-, Shot5=-, Shot6=-, Shot7=- -> **not_real** [] (Shot8 苹果左侧的地面可见一小块浅色碎片，Shot5 苹果左侧也能看到相似碎片；远景中同一区域还有散落的浅色纸片，因此没有明显的跨镜头缺失或变化。)

### priority_190__holocine
- inventory objects - (new -), suspects 4, real 0, USD 0.001514
- S1 [within_shot] Shot3:ge0006 vs  -> **not_real** [] (左侧玻璃柜下层的浅棕色编织篮在第0帧和第5帧可见；第2帧人物经过柜前造成遮挡，未显示出篮子发生变化或无故消失。)
- S2 [cross_shot] Shot3:ge0005 vs Shot4=- -> **unclear** [] (Shot3 中左侧玻璃柜及柜内瓶罐清晰可见。Shot4 的画面只露出最左侧一小段区域，柜内货架没有充分呈现，无法判断这些物品是否缺失。)
- S3 [cross_shot] Shot3:ge0006 vs Shot4=- -> **not_real** [] (Shot3中左侧玻璃柜下层可见一个浅棕色编织篮。Shot4的画面只露出左边缘，柜内下层位置未入镜，因此看不到篮子可由取景范围解释。)
- S4 [cross_shot] Shot3:Shot3/o1 vs Shot4=- -> **not_real** [] (Shot3 左侧边缘可见墙上的浅色管状结构。Shot4 是更近的斜俯视构图，左侧柜子及其后方的墙边区域均未入镜，不能据此判定物体缺失。)

### priority_124__holocine
- inventory objects - (new -), suspects 5, real 2, USD 0.011269
- S1 [within_shot] Shot5:Shot5/o1 vs  -> **not_real** [] (三帧中灯座下方桌面前缘都可见同一小型深色扁平矩形物；第3帧被手和打火机部分遮挡，第5帧打火机置于其旁边，未见物件本身发生变化或消失。)
- S2 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **real** ['Shot1', 'Shot5'] (Shot1 在小桌上可见一盆暗红色小盆栽，带稀疏的尖叶；Shot5 同一盏灯旁的小桌及其台面可见，但没有这盆植物，且未见搬走或遮挡它的动作。)
- S3 [cross_shot] Shot1:Shot1/o2 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **real** ['Shot1', 'Shot5'] (Shot1 的小桌上，红色花盆右侧可见一个细小的深色直立摆件；Shot5 展示同一灯角的小桌时，该位置没有直立摆件，桌面上只有一个扁平的深色物件，画面中看不到能解释这一差异的遮挡或动作。)
- S4 [cross_shot] Shot4:Shot4/o1 vs Shot2=-, Shot3=-, Shot5=-, Shot6=- -> **not_real** [] (Shot2 与 Shot4 的窗边墙面上都能看到相符的暗色小型墙面物件。Shot6 中相应区域大部分被人物遮挡且取景不同，无法据此认定物件消失；Shot3、Shot5 展示的是灯具一侧的墙面。)
- S5 [cross_shot] Shot5:Shot5/o1 vs Shot2=-, Shot3=-, Shot4=-, Shot6=- -> **not_real** [] (Shot5中小桌面前侧可见一个扁平小物件，与清单所述烟盒相符。Shot3未显示桌面，Shot2、Shot4和Shot6则取景于窗边，烟盒所在位置不在画面内，因此不能据此判定物件缺失。)
- U V1 <- V1 **rejected** [cross_shot/setting_background] n1:unspecified :: Shot1 frame 2 的小桌上可见一盆暗红色花盆、稀疏尖状绿叶的盆栽；Shot5 frame 2 同一灯角的小桌台面可见，但没有这盆植物，桌面陈设不一致。
- U V2 <- V2 **rejected** [cross_shot/object_identity] n2:unspecified :: Shot1 frame 2 的小桌上，暗红色花盆右侧可见一个细小、深色、直立且尖形的摆件；Shot5 frame 2 同一灯角的小桌可见扁平的深色物件，但未见该直立摆件。

### priority_191__holocine
- TARGET 191-A1 [within_shot, likely] block-shaped thing at lower left (chair back, cushion or lower wall panel) :: In the off-colour first frame f0 a block with a rounded top corner at the lower left is pale grey-blue; from f1 on the same outline is pitch black, together with a relighting of the whole room (very dark, clearly visible only when the frame is brightened).
- inventory objects - (new -), suspects 0, real 0, USD 0.0

### priority_174__storymem
- inventory objects - (new -), suspects 4, real 0, USD 0.001759
- S1 [cross_shot] Shot3:ge0001 vs Shot2=- -> **unclear** [] (Shot3中可见窗下沿墙的长木凳。Shot2是从窗外朝室内看的受限视角，窗下区域被窗框和构图遮挡，无法判断长凳是否存在。)
- S2 [cross_shot] Shot3:ge0002 vs Shot2=- -> **not_real** [] (Shot2从窗外窄幅取景，画面只见人物和窗内局部，未展示Shot3中桌子右侧的区域，因此椅子未出现可由视角与构图解释。)
- S3 [cross_shot] Shot3:ge0003 vs Shot2=- -> **unclear** [] (Shot3 中拱形开口上方可见一盏小型深色壁灯。Shot2 是从窗外望入的局部视角，画面未清楚呈现拱形开口及其上方墙面，因此无法判断该灯是否缺失。)
- S4 [cross_shot] Shot3:Shot3/o1 vs Shot2=- -> **not_real** [] (Shot2是隔着窗扇向室内看的受限视角，画面只露出人物周围一小部分昏暗背景；Shot3所示后方角落的架子可能被取景范围或人物遮挡，不能据此认定摆件消失。)

### priority_099__storymem
- inventory objects - (new -), suspects 6, real 1, USD 0.008423
- S1 [cross_shot] Shot1:Shot1/o1 vs Shot4=Shot4/o1 -> **real** ['Shot1', 'Shot4'] (两帧都能看到同一街区上方伸出的店铺招牌，但外观明显不同：Shot1 左侧露出蓝色、浅色包边的招牌，Shot4 右上方则是深色长方形、带浅色字样的招牌。画面没有显示足以解释这种颜色和样式差异的遮挡或视角变化。)
- S2 [cross_shot] Shot1:Shot1/o2 vs Shot4=- -> **unclear** [] (Shot1是紧景，画面没有清楚呈现所述招牌上方的墙面；Shot4虽然展示了店面，但角度和取景无法确认是否包含该固定件所在位置，因此不能判断它是否缺失。)
- S3 [cross_shot] Shot2:Shot2/o1 vs Shot3=- -> **not_real** [] (Shot2 左侧背景可见蓝色招牌的一部分；Shot3 是反向近景，画面主要取景在木门与人物上，招牌所在的远左侧立面不在画面内，因此不能据此判定招牌缺失。)
- S4 [cross_shot] Shot2:Shot2/o2 vs Shot3=- -> **not_real** [] (Shot3采用门口附近的反向近景，画面主要是木门和人物，没有覆盖Shot2中排水管所在的背景立面，因此不能据此认定管子缺失。)
- S5 [cross_shot] Shot2:Shot2/o3 vs Shot3=- -> **not_real** [] (Shot2 左侧背景可见浅色立面上的深框窗；Shot3 是反向近景，画面主要取景在木门及其玻璃嵌板，Shot2 所示的左侧背景位置未被拍入，不能据此判定窗户缺失。)
- S6 [cross_shot] Shot4:Shot4/o1 vs Shot1=Shot1/o1 -> **not_real** [] (两帧都能看到街边的悬挑招牌：Shot1 中招牌被截在画面左缘，Shot4 中从另一视角看到其较宽的深色面。视角和取景差异足以解释外观与位置的不同，未见明确矛盾。)
- U V1 <- V1 **rejected** [cross_shot/object_identity] n1:unspecified n2:unspecified :: 两镜头中街边店铺上方伸出的招牌外观不同：Shot1 左侧边缘可见一块蓝色、带浅色边框的窄招牌；Shot4 右上方可见一块深色长方形招牌，带浅色字样。

### priority_085__storymem
- inventory objects - (new -), suspects 1, real 0, USD 0.000445
- S1 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot3=-, Shot4=- -> **not_real** [] (Shot2与Shot3的远景中都能看到楼梯两侧边缘的高大浅色石柱。Shot1和Shot4是人物近景，柱子所在位置未进入画面，因此不能据此判定柱子缺失。)

### priority_050__storymem
- inventory objects - (new -), suspects 8, real 2, USD 0.01099
- S1 [cross_shot] Shot1:ge0001 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (Shot1中可见通道上方的吊灯；Shot2至Shot4都是人物近景，画面未包含该吊灯所在的天花板区域，因此不能据此判断灯缺失。)
- S2 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=- -> **not_real** [] (Shot1 中可见包裹货垛下方的浅棕色木托盘；Shot2 和 Shot4 的近景左下方也能看到相同的木质托盘，未见不一致。Shot3 的相关区域被前景人物遮挡或未充分呈现，不能据此认定托盘缺失。)
- S3 [cross_shot] Shot2:ge0002 vs Shot1=-, Shot3=-, Shot4=- -> **not_real** [] (Shot2与Shot4中浅色货包下方都能看到相同的深蓝色、带光泽的横向平台；Shot1的远景中也可见对应的深蓝色横带，未见无法解释的缺失或变化。)
- S4 [cross_shot] Shot2:ge0003 vs Shot1=-, Shot3=-, Shot4=Shot4/o1 -> **real** ['Shot2', 'Shot1', 'Shot4'] (Shot2和Shot4在浅色货垛下方、女子右侧能看到带深色标签的棕色纸箱；Shot1对应货垛底部及周边地面可见，但没有该纸箱，构成未解释的跨镜头布景差异。)
- S5 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot3=-, Shot4=- -> **not_real** [] (Shot2中浅色包裹物下方可见棕色木质支撑，Shot1的宽景也显示木托盘/木质支撑托着仓库里的包裹物。其他近景的取景范围不足以证明这些支撑缺失，因此没有可确认的不一致。)
- S6 [cross_shot] Shot3:Shot3/o1 vs Shot1=-, Shot2=-, Shot4=- -> **not_real** [] (Shot3中浅色和橙色货垛上方可见深灰色横向波纹金属面；Shot1右上方货垛后方也露出类似的波纹面，符合该背景物仍在场的情况。Shot2和Shot4是人物近景，未显示该物所在的上方背景区域。)
- S7 [cross_shot] Shot3:Shot3/o2 vs Shot1=-, Shot2=-, Shot4=- -> **not_real** [] (各镜头可见的浅色包裹货垛底部都有木质托盘或木板支撑；Shot3左侧托盘虽被前景遮挡，其他镜头也能看到相同类型的托盘，没有明显不一致。)
- S8 [cross_shot] Shot4:Shot4/o1 vs Shot1=-, Shot2=ge0003, Shot3=- -> **real** ['Shot4', 'Shot1'] (Shot2和Shot4都能看到浅色货垛底部旁有带深色标签的棕色纸箱；Shot1的广角画面呈现了女子旁边货垛底部及相邻地面，却看不到该纸箱，且没有明显遮挡解释其缺失。)
- U V1+V2 <- V1,V2 **rejected** [cross_shot/object_identity] ge0003:unspecified n1:unspecified :: 浅色货垛旁带深色标签的棕色矩形纸箱在Shot2和Shot4中可见；Shot1展示女子旁相应浅色货垛底部及邻近地面时未见该纸箱。

### priority_148__wan21
- TARGET 148-A1 [cross_shot, likely] background building beyond the tan outbuilding :: On the open side beyond the outbuilding wall, Shot6 shows a dry field with a distant low single-story beige house and trees, while Shot8 shows a tall multi-story building with balcony-like floor bands and green shrubs on the same side; the camera direction may differ, so this is not certain.
- inventory objects - (new -), suspects 12, real 1, USD 0.015221
- S1 [within_shot] Shot3:Shot3/o2 vs  -> **not_real** [] (第0帧门槛内可见一条浅棕色垫子，说明它并非缺失；第5帧人物挡住了门口区域，垫子不可见可由遮挡解释。)
- S2 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot6=- -> **not_real** [] (Shot2是人物近景，背景为树木和车辆；Shot6也采用人物近景，画面未呈现Shot1中绿布与窗户之间的房屋基部位置。花灌木所在处在这两帧中不可见，不能据此判定为缺失。)
- S3 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot6=- -> **unclear** [] (Shot2中树干后方可见浅色背景，但Shot1和Shot6的取景角度及背景区域不同，无法确认是否包含该短栅栏应在的位置。现有画面不足以判断栅栏是缺失还是被遮挡或未入镜。)
- S4 [cross_shot] Shot3:Shot3/o1 vs Shot5=-, Shot7=- -> **unclear** [] (Shot3 中绿布下方可见一块深色区域，但 Shot5 的近景被杂草遮挡且未拍到该位置；Shot7 的门口区域也被木床遮住，无法确认地垫是否缺失。)
- S5 [cross_shot] Shot3:Shot3/o2 vs Shot5=-, Shot7=- -> **unclear** [] (Shot3 的门口大部分被绿色布帘遮住，地面上的深色痕迹无法确认是门内地毯。Shot5 未拍到门口，Shot7 虽拍到白门，但门槛附近被人物和花床遮挡，无法判断地毯是否缺失。)
- S6 [cross_shot] Shot3:Shot3/o3 vs Shot5=-, Shot7=- -> **unclear** [] (Shot3中烤架右侧地面可见一段深色弯曲软管，但Shot5和Shot7的画面没有清楚展示烤架旁、灌木边的对应位置。现有画面无法判断软管是否缺失。)
- S7 [cross_shot] Shot3:Shot3/o4 vs Shot5=-, Shot7=- -> **unclear** [] (Shot3可见露台右下边缘有一小块亮绿色草地，但Shot5和Shot7的取景没有显示该露台边缘，因此无法判断草地是否缺失或发生变化。)
- S8 [cross_shot] Shot6:Shot6/o1 vs Shot1=-, Shot2=- -> **unclear** [] (Shot6中可见窗旁墙上的两块浅色牌板，但Shot1的对应墙面较远且部分被人物及绿色遮布影响，无法确认牌板是否缺失。Shot2没有清楚展示这处墙面，因此这些画面不足以判定存在不一致。)
- S9 [cross_shot] Shot7:ge0001 vs Shot3=-, Shot5=- -> **not_real** [] (Shot7 的窗内可见浅灰绿色窗帘；Shot3 展示的是另一处门口及绿布遮挡的入口，未显示该窗，Shot5 又是墙面和人物的近景，窗户均不在可比画面内。)
- S10 [cross_shot] Shot7:ge0002 vs Shot3=-, Shot5=- -> **not_real** [] (Shot7 的窗内可见浅灰绿色窗帘；Shot3 画面左侧是另一处白色门，Shot5 只拍到墙面近景，都没有清楚展示这扇窗，因此不能据此判断窗帘缺失。)
- S11 [cross_shot] Shot7:Shot7/o1 vs Shot3=-, Shot5=- -> **real** ['Shot7', 'Shot3'] (Shot7中白门右侧的灰色墙面可见一个白色矩形百叶通风口；Shot3同一门旁的墙面清晰可见，却没有该通风口，画面也没有明显遮挡或取景原因解释其缺失。)
- S12 [cross_shot] Shot7:Shot7/o2 vs Shot3=-, Shot5=- -> **unclear** [] (Shot7中可见浅色花盆及稀疏植株，位于花坛右侧、 pedestal basin 左侧。Shot3和Shot5的画面没有展示这一具体位置，无法据此判断其他镜头中是否缺少该物体。)
- U V1 <- V1 **confirmed** [cross_shot/setting_background] n1:unspecified :: 灰房屋的墙面通风口在Shot7可见：白门右侧、基座盆景左上方有一个带深色窄边的白色矩形百叶通风口；Shot3中白门右侧至烤架左侧的对应灰色墙面可见，却没有该通风口。

### priority_086__wan21
- TARGET 086-A1 [within_shot, clear] second bald bearded man (extra person, duplicate of the prompt's man) :: A second near-identical bald, bearded man in a dark tank top, only the top of his head visible behind the seated man at f0, sits at the table from f1 on while the first man stands and walks to the woman, although the prompt has only one man.
- TARGET 086-A2 [within_shot, likely] walking copy of the bald bearded man :: The copy who stood up and walked over, partly visible bending behind the kneeling woman at f4, is gone at f5 with no exit, leaving only the seated copy; which copy is the prompt's man is ambiguous (by the prompted action it is this one).
- inventory objects - (new -), suspects 6, real 2, USD 0.009214
- S1 [within_shot] Shot4:ge0001 vs  -> **not_real** [] (疑似坐在桌旁的男人在各帧都能看到：第0帧大部分被前景男人遮挡，第1帧清楚露出，第5帧仍坐在桌旁。位置与可见程度的差异可由遮挡解释。)
- S2 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=- -> **real** ['Shot1', 'Shot2'] (Shot1中男子头肩右侧有明显的明亮矩形窗状开口；Shot2中同一男子及其右侧背景都可见，但该处是连续的木板墙，没有对应开口，画面中也看不出遮挡或其他原因。)
- S3 [cross_shot] Shot4:ge0001 vs Shot1=-, Shot2=-, Shot3=- -> **real** ['Shot2', 'Shot4'] (Shot4 的文字描述同一名男子从桌边起身并走向女子，但该帧中桌边仍坐着一名与行走男子外形相似的光头胡须男子，形成未解释的重复。Shot2 中背景仅见一名这样的男子，支持这是人物数量不一致。)
- S4 [cross_shot] Shot4:ge0002 vs Shot1=-, Shot2=-, Shot3=- -> **not_real** [] (Shot4 中左侧桌面上可见一簇点燃的奶油色柱状蜡烛；Shot1、Shot2、Shot3 都是人物近景，未拍到桌面及蜡烛所在位置，因此不能据此判定蜡烛缺失。)
- S5 [cross_shot] Shot4:Shot4/o1 vs Shot1=-, Shot2=-, Shot3=- -> **not_real** [] (Shot4中可见桌子后方左侧的深色木门；Shot1、Shot3是紧景，Shot2也未能确认拍到门所在的左侧墙面，因此门未出现可由取景范围解释。)
- S6 [cross_shot] Shot4:Shot4/o2 vs Shot1=-, Shot2=-, Shot3=- -> **unclear** [] (Shot4中椅子后方的低墙处可见一个小浅色矩形物体，但Shot1至Shot3都是近景，未能看清这一处墙面。现有画面无法判断其他镜头中该插座是否缺失。)
- U V1 <- V1 **rejected** [cross_shot/setting_background] n1:unspecified :: 同一房间中，Shot1男子头肩右侧的背景可见明亮的竖向矩形开口；Shot2相应背景区域则是木板墙，未见该开口。
- U V2 <- V2 **confirmed** [cross_shot/instance_count] ge0001:unspecified :: Shot2画面中只有一名坐着的光头胡须男子；Shot4中桌边有一名坐着的光头胡须男子，同时另一名外形相似的光头胡须男子也出现在画面中并向女子移动，形成两名男子同时出现的重复个体。

### priority_061__wan21
- TARGET 061-A1 [within_shot, clear] second black-shirted man (duplicate person) :: A second man who looks like the Black-shirted man appears while the original still stands at the railing with his hand raised: a head at the bottom centre in f0, the same man standing at the walkway railing in f1 and leaping in f2; the prompt has only one such man, so one copy is an extra, unprompted person.
- inventory objects - (new -), suspects 2, real 0, USD 0.001436
- S1 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot3=-, Shot4=- -> **unclear** [] (Shot2 左下方的地面被画面边缘和人物遮挡，无法清楚确认碎屑所在位置；其余镜头取景于大厅的其他区域，也看不清这块地面，因此无法判断碎屑是否缺失。)
- S2 [cross_shot] Shot3:Shot3/o1 vs Shot1=-, Shot2=-, Shot4=- -> **not_real** [] (Shot3中可见窗户上方的几条浅色平行灯带；Shot1和Shot2的取景主要对着人物、窗户及栏杆，灯带所在的上方区域未入镜，Shot4也没有显示同一窗户上方的位置。现有画面不能证明灯带缺失，差异可由取景角度和构图解释。)

### priority_141__wan21
- TARGET 141-A1 [within_shot, likely] yellow wedge at the mouse's mouth (cheese-like piece) :: A bright yellow wedge-shaped object, looking like a piece of cheese, sticks out of the mouse's open mouth in f1 and is gone from f2 on with no visible cause; it could instead be an oversized yellow tooth.
- inventory objects - (new -), suspects 4, real 1, USD 0.007796
- S1 [within_shot] Shot1:Shot1/o1 vs  -> **real** ['Shot1'] (第0、1帧中鼠旁根部可见区域没有粉色小花，第5帧同一位置却出现一朵花，且没有进入画面或被取出的动作解释这一变化。)
- S2 [within_shot] Shot4:ge0001 vs  -> **not_real** [] (表面右侧与树根之间的暗色区域在第0、1帧已可见，并非只在第3帧出现的独立物体。第3帧老鼠进入该处，符合画面中的动作，不构成未解释的不一致。)
- S3 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=- -> **unclear** [] (粉色小物只在 Shot1 的一帧中出现在鼠鼠手旁。其余画面多为近景或鼠鼠手部所在位置被遮挡、裁出画面，无法确认相同位置是否缺少该物体。)
- S4 [cross_shot] Shot4:ge0001 vs Shot1=-, Shot2=-, Shot3=- -> **unclear** [] (Shot4镜面右侧可见一片暗区，但无法辨认出独立物体；其他镜头的构图也不足以确认是否展示了同一处位置，因此无法判断它是否缺失或发生变化。)
- U V1 <- V1 **uncertain** [within_shot/presence_instability] n1:unspecified :: Shot1中，鼠旁树根前、靠近鼠伸向右侧的手和尾部末端的位置，在第0至4帧均未见粉色小花；第5帧该处突然出现一朵亮粉色小花状物，期间没有显示其进入或被放置的过程。

### priority_143__wan22
- TARGET 143-A1 [cross_shot, likely] auditorium seats :: Shot5's background shows rows of empty theater seats with no audience, while the same venue in Shot1 is packed with a standing crowd behind barriers and shows no seating at all.
- TARGET 143-A2 [within_shot, likely] stadium ribbon-board lettering :: Large white lettering ('ULSEURITY') on the cyan ribbon board above the stands in f0 is gone from f1 on, where the same band is plain cyan with only a small white panel although the camera has not moved (could be an animated display).
- inventory objects - (new -), suspects 14, real 2, USD 0.01844
- S1 [within_shot] Shot1:ge0001 vs  -> **not_real** [] (第3帧右侧边缘的黑色杆状物与前两帧警员手持的警棍相符；人物移动并被画面裁切，足以解释它只在该帧边缘可见。)
- S2 [within_shot] Shot6:Shot6/o2 vs  -> **not_real** [] (蓝白色设备架在第0、1帧都位于画面右下方，后续被经过的红色气球遮挡，变化有明确遮挡原因。)
- S3 [cross_shot] Shot1:ge0001 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **not_real** [] (Shot1右侧边缘可见一个小型深色麦克风状物体，但其他镜头是不同角度或不同区域的近景，没有清楚展示该舞台边缘的位置，因此看不到它可由取景范围解释。)
- S4 [cross_shot] Shot2:ge0002 vs Shot1=-, Shot3=-, Shot4=-, Shot5=- -> **unclear** [] (Shot2 中桌子所处的右侧墙面区域被警员和画面边缘遮挡，无法确认桌子是否在场。其他镜头展示的是场馆的不同区域或不同构图，不能据此判断该桌子缺失。)
- S5 [cross_shot] Shot2:ge0003 vs Shot1=-, Shot3=-, Shot4=-, Shot5=- -> **unclear** [] (Shot2 左侧背景被气球及人物遮挡，无法确认小桌是否实际可见；其他镜头也未清楚呈现同一处背景，因此不能据此判定桌子缺失。)
- S6 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot3=-, Shot4=-, Shot5=- -> **not_real** [] (Shot2中右上墙面可见横向格栅通风口；其他画面取景于舞台边、金属围栏区域或地面，没有展示这面墙，因此看不到通风口并不构成不一致。)
- S7 [cross_shot] Shot2:Shot2/o2 vs Shot1=-, Shot3=Shot3/o2, Shot4=-, Shot5=- -> **real** ['Shot2', 'Shot3'] (Shot2顶部可见一枚由短杆悬挂的黑色圆筒状设备；同场地的Shot3对应区域则出现固定在金属架上的黑色盒状设备，形状与安装方式不一致，画面中没有可见原因解释这种差异。)
- S8 [cross_shot] Shot3:ge0004 vs Shot1=-, Shot2=-, Shot4=-, Shot5=- -> **real** ['Shot3', 'Shot4'] (Shot3与Shot4都呈现同一金属框架区域；Shot3栏杆后有一对明显的圆形彩色LED灯，而Shot4可见的框架区域只有上方蓝色灯点，没有这对灯，画面中也看不到遮挡它们的物体。)
- S9 [cross_shot] Shot3:Shot3/o1 vs Shot1=-, Shot2=-, Shot4=-, Shot5=- -> **unclear** [] (Shot3中金属架后方的黑色线缆清晰可见，但其他画面没有清楚呈现同一组灯具及其后方位置。Shot4虽有金属框架，视角和构图不同，无法确认线缆所在区域是否被拍到，因此不能判定为缺失。)
- S10 [cross_shot] Shot3:Shot3/o2 vs Shot1=-, Shot2=Shot2/o2, Shot4=-, Shot5=- -> **unclear** [] (Shot3中可见目标是金属架旁带蓝色部件的盒状设备，但其他帧没有清楚展示其所在的同一位置。Shot2顶部的圆筒状悬挂物无法确认是同一设备，其他画面也可能因取景角度而未拍到目标位置。)
- S11 [cross_shot] Shot4:Shot4/o1 vs Shot2=-, Shot3=-, Shot5=-, Shot6=- -> **not_real** [] (Shot3 的金属框架旁可见弯曲的深色线缆，与 Shot4 所述的背景线缆相符。Shot2、Shot5、Shot6 的取景分别侧重其他区域或地面，未能显示该线缆所在位置，不能据此认定它缺失。)
- S12 [cross_shot] Shot5:Shot5/o1 vs Shot2=-, Shot3=-, Shot4=-, Shot6=- -> **not_real** [] (Shot5中可见地面活动区后方的深色座椅，但其他镜头取景于场馆不同区域或角度，未显示该座椅所在的背景位置。现有画面无法证明座椅在这些镜头中本应可见，因此不构成已证实的不一致。)
- S13 [cross_shot] Shot6:Shot6/o1 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **not_real** [] (Shot6中人群上方可见青蓝与白色横向标牌；其他镜头是人物近景、金属围栏区域或舞台地面视角，没有清楚展示该标牌所在的上方人群背景，因此其未出现可由取景范围和视角解释。)
- S14 [cross_shot] Shot6:Shot6/o2 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **unclear** [] (Shot6中可见人群护栏末端旁有一件蓝白色设备，但其他镜头没有清楚呈现这一护栏末端及其附近区域，无法据此判断设备是否缺失。)
- U V1 <- V1 **rejected** [cross_shot/object_identity] n1:unspecified n2:unspecified :: Shot2画面上方偏左的黑色设备呈由短杆悬挂的圆筒状；Shot3画面右侧金属架旁的黑色设备则呈带蓝色部件的盒状并固定在架上，二者的外形和安装方式不同。
- U V2 <- V2 **rejected** [cross_shot/object_identity] ge0004:unspecified :: Shot3男子右后方、金属栏杆之间可见上下排列的一对圆形多色LED灯；Shot4可见金属框架和栏杆，但该区域未见这对灯，仅见框架上方的蓝色灯点。

### priority_107__wan22
- TARGET 107-A1 [cross_shot, clear] plaid bedspread on the young man's bed :: In Shot5 the seated young man sits on a bold beige/blue/black plaid bedspread that covers the bed, but in the directly following close view of his lap on the same bed (Shot6) the surface under and around his thighs is plain white sheeting with no plaid spread.
- inventory objects - (new -), suspects 10, real 3, USD 0.018266
- S1 [within_shot] Shot1:ge0002 vs  -> **not_real** [] (墙上画框在各帧中保持一致；人物遮挡了画框的一部分或大部分，未见无法解释的变化。)
- S2 [within_shot] Shot1:Shot1/o1 vs  -> **not_real** [] (第0、1帧左下方可见灯旁的窄桌面；第2、3帧该处被人物身体遮挡，桌面不再清晰可见，不能判定为无故消失。)
- S3 [cross_shot] Shot1:ge0001 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **real** ['Shot1', 'Shot3'] (Shot1右侧墙上的画框虽只露出一部分，画面看起来偏暗且带浅色衬边；Shot3同一侧墙上可见的画框却是醒目的彩色篮球图案，内容明显不一致。)
- S4 [cross_shot] Shot1:ge0002 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **unclear** [] (Shot1中可见男子右后方的小画，但其他画面没有清楚展示与它对应的墙面位置。Shot2的百叶窗旁区域被画面边缘截断，Shot3和Shot5也无法确定其拍到的是同一处墙面，因此不能判断画是否缺失。)
- S5 [cross_shot] Shot1:ge0003 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **unclear** [] (Shot1左侧边缘可见一小段浅色灯罩，但其位置大多被裁切。其他画面没有清楚呈现灯具所在的具体位置，无法判断灯是否缺失。)
- S6 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=-, Shot5=- -> **not_real** [] (Shot1中桌面只在画面左下角、灯具旁露出一小部分；其他镜头取景角度不同，且Shot5左侧被人物和抱枕遮挡，未能确认该处出现了不一致。没有清楚证据表明这张小木桌在可见的同一位置消失或变成了别的物件。)
- S7 [cross_shot] Shot2:ge0004 vs Shot1=-, Shot3=-, Shot4=-, Shot5=- -> **not_real** [] (Shot2中电视及其下方的深色木质电视柜清晰可见。其他镜头采用不同方向或更紧的取景，没有显示电视所在的位置，因此不能据此认定电视柜缺失。)
- S8 [cross_shot] Shot5:ge0005 vs Shot3=-, Shot4=-, Shot6=-, Shot7=- -> **real** ['Shot5', 'Shot3'] (Shot5中站立女子左侧清楚可见一件深红棕色木质柜子；Shot3同一侧的画面露出女子旁的墙面，却看不到这件柜子，未见遮挡或动作能解释差异。)
- S9 [cross_shot] Shot5:ge0006 vs Shot3=-, Shot4=-, Shot6=-, Shot7=- -> **real** ['Shot5', 'Shot3'] (Shot5 的宽景中，站立女子左后方清楚可见一只深棕色木柜；Shot3 也呈现卧室左侧及女子身后的墙面，却看不到该柜，文本也没有说明它被移走或遮挡。)
- S10 [cross_shot] Shot5:ge0007 vs Shot3=-, Shot4=-, Shot6=-, Shot7=- -> **not_real** [] (Shot5左下方可见木椅，但其他画面没有清楚展示椅子所在的木家具旁位置；Shot3的取景方向不同，Shot4、Shot6和Shot7也都是局部或近景。因此无法据此认定木椅缺失。)
- U V1 <- V1 **uncertain** [cross_shot/object_identity] ge0001:unspecified :: 卧室墙上的画框在Shot1右侧边缘（frame 3）仅露出一部分，画内可见暗色图像；Shot3同一侧墙上的画框（frame 2）则清楚呈现橙色篮球图案，画面内容不同。
- U V2+V3 <- V2,V3 **rejected** [cross_shot/setting_background] ge0005:unspecified ge0006:unspecified :: 卧室画面左侧边缘的高大深色木柜在Shot5（frame 3）清晰可见，带有柜门和深色竖把手；Shot3（frame 2）对应的左侧区域显示为格纹墙面，未见该木柜。

### priority_140__wan22
- inventory objects - (new -), suspects 1, real 1, USD 0.005544
- S1 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot3=-, Shot4=- -> **real** ['Shot1', 'Shot2', 'Shot3'] (Shot1 的山脊前景可见连续散布的草丛，而 Shot2 和 Shot3 所示的同一山脊地面主要是裸露碎石，草丛明显缺失。地面位置清楚可见，画面中没有遮挡或动作能解释这一差异。)
- U V1 <- V1 **rejected** [cross_shot/setting_background] n1:unspecified :: 同一山脊的地表在 Shot1 与 Shot2、Shot3 中不一致：Shot1 前景山脊地面覆盖着明显散布的低矮深色草丛；Shot2、Shot3 可见的山脊地面则主要是裸露碎石和岩石，几乎没有相应草丛。

### priority_036__wan22
- TARGET 036-A1 [cross_shot, likely] two round shrubs below the window :: Two round green shrubs sit below the window behind the drone in Shot2 (f0-f2, before the camera tilts up), while the base of the bay window in Shot1 shows only railings and a grass strip; this assumes Shot2's window is the prompt's same bay window, which is itself rendered as a flat window.
- TARGET 036-A2 [cross_shot, likely] window curtains :: The bay window has white tied-back curtains in its side panes in Shot1, but the window behind the drone in Shot2 (the same bay window per the prompt) has no curtains, only a slatted blind in its right panes.
- inventory objects - (new -), suspects 11, real 3, USD 0.012449
- S1 [within_shot] Shot2:Shot2/o1 vs  -> **real** ['Shot2'] (第2帧房屋底部、凸窗下方仍能看到左右两簇深绿色灌木；第3帧相同区域仍在画面内，但灌木不见，轻微构图变化不足以解释其消失。)
- S2 [cross_shot] Shot1:ge0001 vs Shot2=-, Shot4=- -> **not_real** [] (Shot1中可见门旁的深色壁灯；Shot2和Shot4均为无人机近景，背景只显示窗户及墙面，Shot1所述门旁与车库入口的位置不在画面中，不能据此认定壁灯缺失。)
- S3 [cross_shot] Shot1:ge0002 vs Shot2=-, Shot4=- -> **real** ['Shot1', 'Shot4'] (Shot1 的凸窗玻璃后能看到浅蓝灰色窗帘；Shot4 中对应窗户的可见玻璃区域没有窗帘，且画面中的无人机虽遮住中央部分，但两侧仍可见。)
- S4 [cross_shot] Shot1:ge0003 vs Shot2=-, Shot4=- -> **not_real** [] (Shot1中栏杆旁、飘窗下方可见一个小型蓝灰色带盖箱状物。Shot2和Shot4是无人机近景，垃圾桶所在的地面及栏杆位置未入镜，不能据此认定它缺失。)
- S5 [cross_shot] Shot1:Shot1/o1 vs Shot2=-, Shot4=- -> **unclear** [] (Shot1中窄白门右侧的墙面位置部分被无人机和人物遮挡，面板细节无法确认。Shot2和Shot4是无人机近景，背景只显示窗户附近，未能看到该门旁的墙面，因此无法判断面板是否缺失。)
- S6 [cross_shot] Shot1:Shot1/o2 vs Shot2=-, Shot4=- -> **not_real** [] (Shot1 中车库内部的天花板区域可见，但 Shot2 和 Shot4 都是无人机近景，画面未覆盖车库内部；灯具不在画面中属于取景范围不同，不能据此认定缺失。)
- S7 [cross_shot] Shot1:Shot1/o3 vs Shot2=-, Shot4=- -> **unclear** [] (Shot1 的车库左侧可见一件黄色与黑色的竖立设备。Shot2 和 Shot4 都是无人机近景，车库及该设备所在位置不在画面中，无法判断设备是否缺失。)
- S8 [cross_shot] Shot1:Shot1/o4 vs Shot2=-, Shot4=- -> **unclear** [] (Shot1 能看到昏暗的车库内部，但无法清楚辨认所述储物柜；Shot2 和 Shot4 的画面聚焦房屋另一处，车库位置不在画面中。因此无法判断柜子是否在其他镜头缺失。)
- S9 [cross_shot] Shot1:Shot1/o5 vs Shot2=-, Shot4=- -> **real** ['Shot1', 'Shot4'] (Shot1 的白色凸窗最右侧内窗台上可见一个小的棕褐色物件；Shot4 展示同一凸窗时，该处窗台可见且没有这个物件。Shot2 的窗台被裁出画面，不能用于判断。)
- S10 [cross_shot] Shot2:Shot2/o1 vs Shot1=-, Shot4=- -> **not_real** [] (Shot2 中湾窗下方可见低矮绿植；Shot1 和 Shot4 的对应区域也能看到边缘处的绿植，且远景、近景及栏杆遮挡使其显得较少，不构成明确缺失。)
- S11 [cross_shot] Shot4:Shot4/o1 vs Shot1=-, Shot2=- -> **not_real** [] (Shot1 和 Shot4 中，凸窗左侧砖墙、矮围墙上方都能看到小型黑色壁挂物，位置与外观一致。Shot2 是无人机近景，相关墙面未能清楚呈现，不能据此判定物件缺失。)
- U V1 <- V1 **rejected** [within_shot/presence_instability] n1:unspecified :: Shot2 中，房屋凸窗下方画面底边可见的深绿色低矮灌木簇在第2帧出现；到第3帧，凸窗及其下方区域仍在画面中，但该处看不到这些灌木。
- U V2 <- V2 **rejected** [cross_shot/setting_background] ge0002:unspecified :: Shot1 的白色凸窗玻璃后可见浅色、偏蓝灰的窗帘；Shot4 中同一凸窗的可见玻璃区域未见这些窗帘。
- U V3 <- V3 **rejected** [cross_shot/setting_background] n2:unspecified :: Shot1 白色凸窗最右侧的内窗台边缘可见一个小型、圆钝的棕褐色摆件；Shot4 中凸窗右侧窗台区域仍可见，但未见该摆件。

**val totals**: {"units": 19, "confirmed": 2, "confirmed_unspecified": 2, "videos": 20, "suspects": 109, "real": 21, "objects": 0, "new_objects": 0}


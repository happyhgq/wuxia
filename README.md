ZMUD 武侠单机小游戏 - 项目设计与开发指南 (README)文档说明：本文档旨在记录本项目地图架构、核心机制及数据结构设计。无论是后续由人类开发者继续编写代码，还是切换到其他 AI 助手接续开发，均可阅读本文档快速了解项目全貌并保持架构的一致性。📖 项目简介本项目是一款基于 Python 开发的单机文本武侠 MUD 游戏。游戏采用基于 JSON 配置文件的房间图结构（Room Graph），结合 Zone（区域）隔离机制 与 跨区域传送/连接节点，支持玩家移动、NPC 交互、资源采集、安全区保护、副本探索与黑市暗道等经典 MUD 玩法。   🗺️ 地图与 Zone 架构设计地图采用扁平化的 JSON 字典结构（rooms_2.json），以唯一房间 ID（room_id）作为 Key。   1. Zone（区域）隔离划分地图被划分为若干独立 Zone，便于进行逻辑隔离（如音乐/天气控制、安全区规则、特定指令限制）：   main：新手村（青石村）、周边官道与后山荒野。   bandit_zone：黑风寨副本（高危险区，分布大量敌人与奖励）。   guiyun_city：归云城主城（大型城市，含武馆、镖局、府衙、万商坊等）。   2. 跨区域连接（Gateway / Transition Rooms）区域间通过特定过渡节点或密道进行无缝连通：   新手区 ↔ 主城：official_road_east_2（官道终点）与 guiyun_south_gate（归云城南门）。   新手区 ↔ 副本：cave_entrance（山贼寨门）与 bandit_courtyard（寨内演武场）。   副本单向密道：bandit_back_mountain（黑风后山）可向东连回主大地图的 wild_fields（村后荒野），形成副本出口。   城市暗道/城中城：听风雅间 (guiyun_tea_room) → 七曲巷 (guiyun_qiqu_lane_1/2) → 废弃染坊 (guiyun_dye_house) → 地下暗道 (guiyun_secret_passage) → 沉星黑市 (guiyun_black_market)。   📄 数据结构规范 (rooms_2.json)每个房间节点的标准字段配置如下：   JSON{
  "room_id": {
    "name": "房间名称",
    "zone": "所属区域标识 (main / bandit_zone / guiyun_city)",
    "desc": "房间文本描述，包含环境、提示及可能的操作指令（如 dazuo, search, forge）",
    "exits": {
      "方向(东/南/西/北/上/下)": "目标房间_id"
    },
    "coord": [X坐标, Y坐标],
    "safe": true,
    "npcs": ["NPC名称1", "NPC名称2"],
    "enemies": ["怪物名称1", "怪物名称2"],
    "forage": {
      "物品名称": 掉落概率权重
    }
  }
}
字段说明：exits：邻接图算法核心，控制移动逻辑。   coord：区域内二维相对坐标（[x, y]），用于绘制 2D 小地图（Mini-map）。   safe：安全区标识，true 时逻辑上禁止私斗/PK/刷怪。   forage：资源采集表，配合 search / gather 指令使用。   npcs / enemies：当前房间加载的交互人物或战斗敌人。   🛠️ Python 核心引擎开发路线图后续开发请优先围绕以下几个模块进行逻辑落地：1. 地图与玩家移动模块 (map_engine.py)Pythondef move_player(player, direction, rooms):
    current_room = rooms[player.current_room_id]
    if direction in current_room["exits"]:
        next_room_id = current_room["exits"][direction]
        next_room = rooms[next_room_id]
        
        # 跨区域提示
        if current_room["zone"] != next_room["zone"]:
            print(f"【区域变更】你离开了 {current_room['zone']}，踏入了 {next_room['zone']}！")
            
        player.current_room_id = next_room_id
        display_room(player.current_room_id, rooms)
    else:
        print("那个方向没有路。")
2. 交互与指令解析模块 (command_handler.py)look / l：展示当前房间名称、描述、出口、NPC 及敌人。   search / forage：校验当前房间的 forage 字段，执行概率抽奖。   attack / kill：发起战斗前检查 room.get("safe", False)，若为 true 则拒绝触发战斗。   dazuo / heal：打坐恢复，特定房间（如 temple）提供特殊效果。   3. 小地图渲染模块 (minimap.py)利用房间中的 coord 字段，筛选出玩家当前所在的 zone 内所有房间，在终端使用字符网格打印 2D 局部小地图。   🚀 后续扩展计划 (Backlog)[ ] 马车/车夫系统：在马厩房间（如 guiyun_stable）添加车夫 NPC，支持付费一键传送回新手村 village_gate。   [ ] 动态刷新机制：定时刷新野外/副本房间中的怪物（enemies）与采集资源（forage）。   [ ] 任务与暗号系统：配合黑市暗道，实现特定对白/物品解锁石门入口。   💡 AI 助手接续提示：如果重新打开新会话，直接将本 README 与 rooms_2.json 投喂给 AI，并提示：“请根据 README 中的规范，继续编写 Python 移动引擎/战斗系统/小地图功能”，AI 即可精准接管上下文！

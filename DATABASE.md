<!-- character-story-20261027:start -->
> 2026-10-27：010/011已实测就绪。人物参考与剧情首帧流程、有限GPU、执行中恢复和合成技术Passed；内容NeedReview、发布Blocked。见[完整验收](docs/CHARACTER_STORY_ACCEPTANCE_20261027.md)。
<!-- character-story-20261027:end -->

# 数据库文档入口

详细数据库结构、迁移、备份和恢复规则以 [`docs\DATABASE.md`](docs/DATABASE.md) 为唯一维护源。

数据库初始化和升级必须使用 `scripts\init_database.ps1`；任何迁移前先备份，不删除既有业务数据，不把密码写入仓库。

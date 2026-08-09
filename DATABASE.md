# 数据库文档入口

详细数据库结构、迁移、备份和恢复规则以 [`docs\DATABASE.md`](docs/DATABASE.md) 为唯一维护源。

数据库初始化和升级必须使用 `scripts\init_database.ps1`；任何迁移前先备份，不删除既有业务数据，不把密码写入仓库。

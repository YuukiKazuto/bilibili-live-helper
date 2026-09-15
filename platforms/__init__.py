"""平台弹幕源包：base 定义统一事件模型与抽象基类，各平台各自实现。

新增平台 = 新增 platforms/<name>/ 包实现 PlatformBase，
禁止在 core/ 或 tts/ 中出现平台分支判断（见 .claude/rules/01-architecture.md）。
"""

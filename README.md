# MCDR-Server-Pivot
在MCDR中通过服务器枢纽管理子线程服务器，这个插件允许你在MCDR下利用子线程启动MCDR，同时支持多个服务器管理，只需要在主终端上输入代码即可

此插件主要在linux上测试，目前尚未在window上测试，但是也写了这部分的代码
文档需要我慢慢填写，我可能很久也不会写完

事实上，我在插件中使用了很多易于理解的设计，希望即使初次使用也能摸索明白

### 我需要感谢：
1. @EMUnion   https://github.com/EMUnion   设计的MirrorServerReforged插件    https://github.com/EMUnion/MirrorServerReforged    ，我用其源代码进行学习后重新写了一次，可能其中会有少部分借鉴，恳请作者理解
2. @tanhHeng  https://github.com/tanhHeng  设计的MirrorMcsmcdR插件    https://github.com/LazyAlienServer/MirrorMcsmcdR    ，我通过使用他的插件获取了很多改进这个插件的灵感
3. 还有Deepseek，我并没有很浓厚的python基础和MCDR插件开发基础，是Deepseek指导我一步步把这个插件写完并给予了很多先进的建议，事实上这个插件有90%是交给Deepseek生成的，我只是做了一个思路提供，整合，修理bug的过程

感谢你们！

最后，如果我的插件在你的MCDR运行中出现了问题或者有更好的建议，欢迎提交给我，我将在有空的时候（也许很久以后）会尝试修改甚至重构代码
希望你们能参加代码优化

## 让我们开始吧

首先，你需要下载好本插件并放置到MCDR根目录的`plugins`文件夹中

目前本插件不需要安装其他的python支持库

### 使用本插件
首先你需要运行好mcdr主程序，并且建议在运行mcdr的启动命令启动了主服务器后，如果还有在同一个终端创建其他服务器（例如镜像服务器，或者其他服务器）的时候才启用本插件。

## 配置文件
第一次运行此插件时，若配置文件不存在，则会在`config`文件夹中新建一个`MCDR-Server-Pivot.json`文件用于存储配置信息

目前的配置文件结构长这样：
```{
    "config": {
        "enable": False,
        "permission": {
            "main": 1,
            "help": 0,
            "servers": 0,
            "s": 2,
            "start": 2,
            "stop": 2,
            "kill": 2,
            "restart": 2,
            "command": 2,
            "mcdr": 2
        }
    },
    "servers": {
        "mirror": {
            "auto_start": False,
            "path": "./mirror",
            "command": MCDR_Command
        }
    }
  }
  ```
 
### config

这里是插件的主要设置，包括：
`"enable"`插件是否启用（其实目前这个功能没有写，默认为true）
`"permission"`运行插件命令所需要的MCDR权限等级

**值得注意的是，权限等级需要在父级满足后再判断子级，若其中一个级别权限不足则无法执行，例如：**

`"servers"`权限设置为`0`，当`"start"`权限设置为`2`时，`!!msp servers`在`0`权限人员中可以运行`!!msp servers start`在`0`权限人员中不可运行，但在`2`权限人员中可以运行

`"servers"`权限设置为`2`，当`"start"`权限设置为`0`时，`!!msp servers`在`0`权限人员中不可运行`!!msp servers start`在`0`权限人员中也不可运行（因为父级的权限需求为`2`）但在`2`权限人员中可以运行

是不是一段绕口令？其实不管就行了，**默认便好**

### servers

里面装着所有子服务器的配置

`"mirror"`是服务器名称，用于输入命令。例如这种配置下你需要查看这个服务器的状态则输入`!!msp mirror`

`"auto_start"`指的是在主MCDR启动的时候该服务器是否跟随自动启动，当`false`时，每次启动主MCDR都需要手动输入`!!msp s mirror mcdr`启动该子进程
`"path"`指的是该服务器文件的位置，`"./mirror"`意味着文件在MCDR根目录的`mirror`文件夹内
`"command"`指的是启动该服务器时执行的命令，默认为`python3 -m mcdreforged init&&python3 -m mcdreforged`（在linux环境下）,通常来说**默认就好**，此项将会在运行`!!msp s mirror mcdr`或`!!msp s mirror restart`的时候使用该配置

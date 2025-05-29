# knowledge-core

## html 抽取

对于每个站点，编写对应的抽取规则，比如说 `mp.weixin.qq.com`，编写对应的 `mp_weixin.yaml` 作为抽取规则文件，放到 `adapters/html_extractor/rules` 目录下。

注意点

1. 图片需要以 png 格式存储到本地目录，json 文件里记录相对路径；
2. 网页信息需要存储 title, url, author, publish_time 等字段；
3. 目前都是传入 html 文件内容进行抽取，后续可以考虑传入 url 直接抓取网页内容进行抽取，但是优先级不高。
4. html 文件里有记录拉取时间，即 `save_time` 字段，可以考虑存储到 json 里。
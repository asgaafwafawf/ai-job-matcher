# 演示素材

本目录中的演示数据全部为虚构内容（人物“张三”、公司名和岗位链接均为示例），**不包含任何真实简历、联系方式或单位信息**。

## 查看

- 网页界面截图：`screenshots/web_ui.png`
- 报告截图：`screenshots/report_demo.png`
- 可直接打开的静态报告：`demo/report_demo.html`

## 离线重新生成报告

报告生成不需要 API key，使用示例 JSON 即可：

```bash
cp examples/profile.example.json data/profile.json
cp examples/top30.example.json data/top30.json
cp examples/job_pages.example.json data/job_pages.json
python make_report.py
```

然后打开 `output/report_日期.html`。

## 说明

- 示例画像：5 年结构工程师、硕士、深圳、期望 28K
- 示例岗位：AI 应用、结构设计、BIM 研发等虚构岗位
- 示例数据仅用于展示报告样式和字段结构

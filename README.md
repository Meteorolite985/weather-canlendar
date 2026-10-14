# 天气日历（东莞 + 广州）

未来 14 天天气预报生成的 iCalendar 订阅源，由 GitHub Actions 每天北京时间约 06:10 自动更新。

## 订阅地址

在手机自带日历里添加“订阅日历”，粘贴下面的地址：

- 两座城市合并：https://raw.githubusercontent.com/Meteorolite985/weather-canlendar/main/calendar/weather-all.ics
- 广州：https://raw.githubusercontent.com/Meteorolite985/weather-canlendar/main/calendar/weather-guangzhou.ics
- 东莞：https://raw.githubusercontent.com/Meteorolite985/weather-canlendar/main/calendar/weather-dongguan.ics

## 说明

- 每个城市每天一个全天事件，标题含天气与气温，详情含降水概率、降水量、风速、日出日落。
- 数据来源：Open-Meteo。脚本：`weather_calendar.py`
- 手动重跑：`python3 weather_calendar.py --output calendar`

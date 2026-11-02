# University System of Taiwan Graduate_time parser

2020-11-13 : fix some link bug

2018-8-23 update: 支援顯示口試日期

2018-8-18 update: 支援系所過濾

2018-8-17 update: 支援中央、清大、陽明

2026-11-2 update: 修正交大

計算方式：x = 畢業年 - 入學年

x == 1 : 兩年準時畢業 </br>
x == 2 : 兩到三年畢業 </br>
x == 3 : 三到四年畢業 </br>
x >= 4 : 四年以上畢業 </br>

## 使用方式
### 要求下載 uv 

```

uv init -p 3.12
uv sync
```

### run
```

uv run main.py

```
輸入你想要的教授跟學生


僅供參考

# SeatBond

影院连座锁座：按场次厅图查找连续空座，过道列断开，冲突检测既有持座。

## 居中偏好选段

同一场次存在多段可容纳人数的连续空位时，不再固定取最左段，而是：

1. 过道与既有持座共同把每排切成若干自由段，各段分别计分。
2. 得分 = −（段中点到厅中线 `(cols + 1) / 2` 的距离），越近中线得分越高。
3. 选中段内部按居中落位（段长减去人数后的余量，整除余量放在左侧）。
4. 同分稳定次序：排号更小优先，再比起始列更小。该次序在测试中写死。
5. 落库前仍执行与既有持座的重叠检测，冲突写 `conflict_logs` 并返回 409。

`GET /api/trial?showtime_id=&party_size=&preferred_row=` 为试算接口，不落库，
返回按得分排序的候选段列表（排、落座起止列、所在空段、距离、得分）与 `selected`。
随后 `POST /api/holds` 在相同状态下锁定的坐标与试算首选段完全一致。
`preferred_row` 给出时仅在该排内选段；该排放不下时回退到全局最优。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |
| API 文档 | http://localhost:9100/docs |
| Postgres | localhost:5442 |

健康检查：`GET http://localhost:9100/api/health`

## 页面

- `/halls` — 影厅
- `/showtimes` — 场次
- `/seatmap` — 座位图（大网格热力）
- `/hold` — 锁座
- `/orders` — 订单
- `/conflicts` — 冲突

## 使用说明

1. 在影厅与场次页确认厅图与排期。
2. 打开座位图查看占用热力，在锁座页输入连座人数并提交。
3. 订单页查看持座结果；冲突页查看重叠请求。

## 开发与测试

```bash
docker compose exec api pytest -q
```

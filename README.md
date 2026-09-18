# SeatBond

影院连座锁座：按场次厅图查找连续空座，过道列断开，冲突检测既有持座。

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
2. 打开座位图查看占用热力，在锁座页输入连座人数；可先「试算候选段」查看排序，再提交锁座。
3. 订单页查看持座结果；冲突页查看重叠请求。

## 居中偏好评分

同一场次存在多段满足人数的连续空位时，不再固定取最左段，而是按候选块中点到
**厅中线**的距离打分（`score = -|中点 - 厅中线|`，越近越高），只落得分最高的一段。

- 厅中线 = `(1 + 总列数) / 2`（过道列计入列坐标；奇数列厅穿过中央座中轴线）。
- 过道列打断连续段，打断后的各段**分别枚举、分别计分**；既有持座 punched holes 同样断开。
- 每个能容纳 N 人的空段内，滑动枚举所有恰好 N 人的候选块参与排序。
- 同分稳定次序（已写死，见引擎与测例）：① 排号更小优先 → ② 同排起始列更小优先。
- 选中块坐标即落库坐标；锁座响应与 `POST /api/holds/preview` 试算返回同一候选排序，
  锁座页会高亮已锁的一段并标注「与试算最高分段一致」。
- 冲突重叠检测仍在落库前生效，冲突时返回 409 并写 `conflict_logs`。

种子数据中的「三号厅（居中试算）」为 12 列、中央过道 6,7（左右镜像），第 1 排已占
4-5：2 人锁座时旧最左策略落 1-2，居中策略落右区的 **8-9**（距中线 2.0）。

### 试算接口

```
POST /api/holds/preview
{ "showtime_id": 1, "party_size": 2, "preferred_row": null }
```

返回 `hall_center` 与候选列表（`rank, row, start_col, end_col, center, distance, score`），
不落库。`POST /api/holds` 真正锁座，仍只落一段，响应额外携带 `score/distance/candidates`。

## 开发与测试

```bash
docker compose exec api pytest -q
```

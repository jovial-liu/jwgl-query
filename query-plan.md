支持按需查询的几类信息：
1. 课程表 (course_schedule)
2. 考务安排 / 监考安排 (invigilation)
3. 课程考试安排查询 (exam_course_arrangement)
4. 考试信息查询 (exam_info)
5. 考试总查询 (exam_all，聚合 2/3/4)

输出方式：
- 默认 stdout / JSON
- 由 OpenClaw 对话直接返回用户

当前原则：
- 保持按 query-type 查询
- 优先直接在对话里返回结果
- 返回格式跟随用户问题，不使用僵硬模板
- 非必需的通知/落库能力不作为主路径

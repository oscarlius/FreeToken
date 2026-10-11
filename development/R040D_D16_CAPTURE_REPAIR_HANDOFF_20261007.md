# R040d D16 采集修复与剩余24项交接

R040c/b97是工装采样捕获不全；原failed_harness/D04原件保持只读。已有slots2六case和R040a六锚点沿用，R040d只测其余24项（slots4十项、停车四项、缓存四项、交错六项）。不伪造旧交付，不修改任何verdict，不覆盖旧batch。

实际根因：b97第二次预填批含UID1/2完整512、UID3仍384/512；旧sampler_capture.py把UID3的负generation视为整批无效，连带丢弃UID1/2采样，此后的物理历史失配。0aa Engine在完成请求后压紧sampler行；新hook按完成请求的紧凑行顺序捕获，未完成提示行不贡献采样历史。保留原fp32 logits、NPZ/manifest、registry、UID/输入/过程出生及四类PT状态schema；产品代码不改。

新shutdown reader在交付缺失/不完整时点名arm及capture/service_delivery.json路径、expected/verified计数、首个缺失UID/generation。原启动/调度/消息/采样/发送/退出链均保留。完整源新包只叠加3个入口叶子和5个capture来源角色，其他字节继承R040c冻结源码；原角色17项独立复核。

CPU综合28 PASS（含真实三req→两sampler行、4UID×128、重排、未完成提示、缺历史拒绝、完整schema交付及余24入口保留元数据）。正式canonical入口import、D04前置检查和实际owner构造PASS。前置只核清单/round SHA、只读位和D04，保留slots2 group review/pin强SHA绑定，不重读旧原始。
CPU/source包：/data2/FreeToken/runs/dev_D16/r040d_v1_complete_source_cpu_20261007_234521
CPU report SHA：527d2d0957dc95e1781e42f35f5c825498976586a6e1f190dd87bfcc3672b960
collector17-role review SHA：dae4629a781858e82eae6067de19fead38112ec83812f28e31ff10e16c80204e

真实FILEdry已24/24通过：同正式入口/路径/用户完成权限、MD5/哈希、复制、输出写入与动态端口分配；未起服务、发请求、拿锁、分配batch或创建正式RID。R046g/b99外来锁保持。
回执：/data2/_shared/runs/ft_rounds/.dryrun_r040d_20261007_234811/dry_run_receipt.json
SHA：a76a9a279b8d1e49bca3804249f4053df0f5abc95bcd814c0ffc20712261fc9e

最终R启动复核进行中；通过后再排已授权的独立续跑。用户已明确“补齐后重跑batch；新batch目录；不改原始/verdict”，因此本轮按条件授权，不重复请求同一续跑批准；当前GPU仍由b99持有，不能启动重叠测量。配置0aa23431/98,304/0.88；超过旧失败的已完成范围不补造。

最终更新（2026-10-07 23:57）：独立R启动签PASS，root以正式cwd实际require_dry_run_receipt/require_startup_review回读PASS；review SHAeea77bbe51bbd5a2aeec45c47e16e5f208e488425c4d1aecc76415620ea4d3de，pin SHA4da95ddaca06b15b97e6af5aea07d4fac6005bbc8a4a0474196bc20d617facf9。已就绪但b99持锁，排队不并跑。

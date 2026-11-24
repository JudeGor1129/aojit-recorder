# OpenMinis AOJIT 镜像录制器

在 **GitHub Actions 的 Apple Silicon runner** 上录制 OpenMinis 的 AOJIT 镜像（`aot_*.S` + iOS 用的 `.o`）。

公开仓库下 macOS arm64 runner **免费且不限分钟**，一个仓库、点一下按钮就能跑。

## 为什么需要录

OpenMinis 源码里 `deps/aot/` 只有文档和工具，**镜像本体被 gitignore**（约 1 GB 汇编）。
直接编译出来是空的 `libish_aot.a`，App 里 AOJIT 页面 25 行全是 "No image"。

镜像必须在 macOS + Apple Silicon 上用「能生成代码」的 JIT 版 ish 录制；iPhone 上做不了（无 JIT 权限）。

## 跑起来

1. 把本目录推到自己的 **public** 仓库
2. 仓库页 → **Actions** → `Record AOJIT images` → **Run workflow**
3. 默认参数：`ref=1.15`、`modules="musl busybox python"`、`jobs=2`、`ios=true`
4. 约 **40–90 分钟**，产物在 Artifact 里（`aot_*.S` + `aot_*_ios.o`）

命令行等价：

```bash
gh workflow run record-aojit.yml -f ref=1.15 -f modules="musl busybox python"
gh run watch
gh run download -n aojit-images-1.15-run1 -D out
```

## 流程（每一步都有原因，别随手删）

| 步骤 | 说明 |
|---|---|
| 装 meson/ninja/libarchive | libarchive 是 `fakefsify` 的依赖 |
| clone `--branch <ref> --recurse-submodules` | `deps/ish` 必须是**同一个提交**，否则 abi 对不上 |
| 编 `build-arm64-jit`（`-Djit=true -Djit_emit=true`） | 录制**必须**能运行时翻译；App 里那份是 `jit_emit=false`，只能消费镜像 |
| 解压 `alpine-minirootfs-3.21.0` 成**普通目录树** | `record.sh` 用 `ish -r <rootfs>`，而 `-r` 是 **realfs**、`-f` 才是 fakefs（`xX_main_Xx.h` 的 `getopt` 串 `+r:f:d:c:n:`）。把 fakefs 目录传给 `-r` 会报 `xX_main_Xx: No such file or directory` |
| 用未升级的 3.21.0 minirootfs | musl 1.2.5-r8、busybox 1.37.0-r8，与 App 内置 rootfs 完全一致 |
| `apk add`（**不带 `-u`**） | 加了 `-u` 会把 musl/busybox 升到 r11/r14，build-id 就与 App 不匹配了，只能退化成 family matching |
| `install.sh` | 把 `guest/` 拷进 `/tmp/aojit` 并生成输入（需要 python3/numpy/matplotlib/node 已装好） |
| `record_images.sh` | 逐模块录，`IOS=1` 时顺带 `xcrun -sdk iphoneos clang` 汇编 `.o` |

## 产物怎么用

```bash
cp out/aot_*.S  <你的 OpenMinis 检出版本>/deps/aot/
cd <检出> && ./deps/build_ish.sh     # 内部调 build_aot.sh，归档成 libish_aot.a
```

`.S` 由 `-force_load` 链进二进制，App 启动时注册。iOS 的 `.o` 用于 `ISH_AOT_OBJECTS`，二选一即可。

**文件名不要改**：符号是 `_ish_aot_module_<name>`，由文件名推导。

## 三道门禁（镜像能不能被用上）

| 门禁 | 检查方式 | 不匹配的后果 |
|---|---|---|
| **abi** | job summary 里打印；Minis 1.15 应为 `1f3bb5a0` | 直接 `rejected`，等于没录 |
| **build-id** | `image_info.py` 输出 | 降级为 family matching，约 51–93% 的收益 |
| **录制器同源** | `git -C deps/ish rev-parse HEAD` | abi 变化，整批作废 |

job summary 会把这几个值都打出来，**存到镜像旁边**，将来重编才知道对得上哪一版。

## 本地 / 租的 Mac

```bash
./scripts/record-local.sh 1.15 musl busybox python
```

同样的流程，需要 macOS + Apple Silicon + Xcode + Homebrew + 约 12 GB 空闲。

## 常见失败

| 现象 | 原因与处理 |
|---|---|
| `record.sh` 报 `a step failed` | 某个 workload 输出里有 `FAIL/Traceback/not found`，通常是包没装全（python3、node、matplotlib）。看它打印的 5 行日志定位 |
| `apk add` 407 / 解析失败 | runner 到 `dl-cdn.alpinelinux.org` 的网络问题，重跑一次 |
| `image_info.py` 显示 abi 不是 `1f3bb5a0` | `ref` 变了或子模块被更新过，改用 `ref=1.15` 重新跑 |
| 录制中途 OOM | 7 GB 内存吃紧，把 `jobs` 改成 `1` |
| `libish_aot.a` 仍是空的 | 你把 `.S` 放错了目录；必须放 `deps/aot/` 根下，不是 `deps/aot/images/` |

## 边界

- **只适用于 1.15**。公开仓库没有 `v1.16`（tag 指向 1.15 的提交），`ref=1.16` 会直接 clone 失败。等上游同步后改 `ref` 即可，流程不用动。
- **镜像与包版本绑定**。Alpine 3.21 仓库里的 python3 会随时间升级，重录出来的 build-id 与官方 10 月那批不同，正常，只是命中率算法上等价。
- **别指望录全套**。node 605 MB、gh 456 MB，收益还低（gh 是静态二进制、rg 只有 3–6%）。`musl + busybox + python` 覆盖了 Shell 和脚本的绝大多数路径。

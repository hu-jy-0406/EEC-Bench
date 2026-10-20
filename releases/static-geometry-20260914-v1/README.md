# 固定版本 static-geometry-20260914-v1

三种方法及独立 shot 动静划分、质量融合、重投影评测的源码依赖闭包、提示词、输入、输出均在 payload 下；manifest.json 逐文件校验。大权重不复制，保存官方提交与权重 SHA256、当前环境包版本。特别固定 GeoCalib + Boxer 的共享内参/重力、无深度输入、960 输入、固定实体名单与融合规则。

验证：`python EECBench/scripts/freeze_static_geometry_pipeline.py --verify RELEASE_DIR`

此版本固定的是现有固定机位六帧实验。不要把相机平移全零的前端推广到移动相机；换前端/阈值必须创建新版本。不得覆盖此目录。原模型输出已保存，后续评分直接读取冻结 Gs；不重新抽样几何。代码快照是隔离存档，非对整个脏仓库的提交。

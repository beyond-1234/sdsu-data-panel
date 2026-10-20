import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config import Config
from models import db, User, Dataset, Keyword, DownloadLog, StorageConfig, VariableDefinition, SiteLocation
from services.data_parser import (
    generate_sample_clm_timeseries,
    parse_dataset_timeseries,
    get_depth_profile_data,
    calculate_kinetics_curve
)
from services.stats_service import get_dashboard_summary
from services.oss_service import upload_to_oss, get_oss_download_url, get_active_oss_config
from services.i18n import TRANSLATIONS

app = Flask(__name__)
app.config.from_object(Config)

# 初始化插件
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = '请先登录科研账号以进行此项操作'
login_manager.login_message_category = 'info'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ----------------- 国际化 i18n 注入与切换 -----------------
@app.context_processor
def inject_i18n():
    current_lang = session.get('lang', 'zh')
    if current_lang not in ('zh', 'en'):
        current_lang = 'zh'
    
    def t(key, *args):
        lang_dict = TRANSLATIONS.get(current_lang, TRANSLATIONS['zh'])
        val = lang_dict.get(key, TRANSLATIONS['zh'].get(key, key))
        if args:
            try:
                return val.format(*args)
            except Exception:
                return val
        return val

    return {
        'current_lang': current_lang,
        't': t
    }

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ('zh', 'en'):
        session['lang'] = lang
    next_page = request.referrer or url_for('index')
    return redirect(next_page)

# ----------------- 数据库初始化与初始数据 Seed -----------------
def seed_database():
    with app.app_context():
        db.create_all()

        # 1. 确保基础管理员与默认科研用户存在
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin = User(
                username='admin',
                email='admin@sdsu.edu',
                role='admin',
                institution='SDSU Ecohydrology Lab'
            )
            admin.set_password('admin123')
            db.session.add(admin)

        researcher = User.query.filter_by(username='researcher').first()
        if not researcher:
            res = User(
                username='researcher',
                email='researcher@cas.ac.cn',
                role='user',
                institution='Institute of Geographic Sciences and Natural Resources Research, CAS'
            )
            res.set_password('res123')
            db.session.add(res)

        db.session.commit()

        # 2. 初始预置关键词 (对标 MicrobialDataSystem 与土壤微生物生态学术语)
        default_keywords = [
            'soil_microbial_biomass',
            'microbial_biomass_c',
            'microbial_biomass_n',
            'microbial_biomass_p',
            'fungal_biomass',
            'bacterial_biomass',
            'fungal_bacterial_ratio',
            'soil_doc',
            'soil_respiration',
            'metabolic_quotient',
            'microbial_stoichiometry',
            'arctic_tundra',
            'peatland_wetland',
            'forest_soil',
            'soil_ph'
        ]
        kw_map = {}
        for kw_name in default_keywords:
            kw_obj = Keyword.query.filter_by(name=kw_name).first()
            if not kw_obj:
                kw_obj = Keyword(name=kw_name)
                db.session.add(kw_obj)
                db.session.flush()
            kw_map[kw_name] = kw_obj
        db.session.commit()

        # 2.1 初始预置标准化科学变量指标字典 (对标 MicrobialDataSystem 真实表头与变量)
        default_variables = [
            # 微生物生物量与化学计量比 (Microbial Biomass & Stoichiometry)
            ('MBC', '土壤微生物量碳 (Microbial Biomass C)', 'Soil Microbial Biomass Carbon', 'Microbial Pool', 'mmol kg-1', '土壤活体微生物细胞碳总储量 (Chloroform fumigation extraction)', 'Total living microbial biomass carbon in soil'),
            ('MBN', '土壤微生物量氮 (Microbial Biomass N)', 'Soil Microbial Biomass Nitrogen', 'Microbial Pool', 'mmol kg-1', '土壤活体微生物细胞氮总储量', 'Total living microbial biomass nitrogen in soil'),
            ('MBP', '土壤微生物量磷 (Microbial Biomass P)', 'Soil Microbial Biomass Phosphorus', 'Microbial Pool', 'mmol kg-1', '土壤活体微生物细胞磷总储量', 'Total living microbial biomass phosphorus in soil'),
            ('FBC', '真菌生物量碳 (Fungal Biomass C)', 'Fungal Biomass Carbon', 'Microbial Pool', 'g C m-2', '土壤活跃真菌菌丝碳储量', 'Explicit active fungal mycelial carbon pool'),
            ('BBC', '细菌生物量碳 (Bacterial Biomass C)', 'Bacterial Biomass Carbon', 'Microbial Pool', 'g C m-2', '土壤活跃细菌细胞碳储量', 'Explicit active bacterial carbon pool'),
            ('Q_MET', '微生物代谢商 (Metabolic Quotient, qCO2)', 'Microbial Metabolic Quotient (qCO2)', 'Microbial Pool', 'mg C g-1 MBC h-1', '单位微生物生物量的呼吸消耗速率', 'Specific soil respiration rate per unit microbial biomass'),

            # 土壤碳氮理化 (Soil Chemistry & Physics)
            ('SOC', '土壤有机碳 (Soil Organic Carbon)', 'Soil Organic Carbon', 'Soil Physics', 'mmol kg-1', '土壤固相总有机碳含量', 'Total organic carbon content in soil matrix'),
            ('TN', '全氮 (Total Nitrogen)', 'Total Soil Nitrogen', 'Soil Physics', 'mmol kg-1', '土壤全氮素含量', 'Total nitrogen content in soil matrix'),
            ('TOP', '土壤全有机磷 (Total Organic Phosphorus)', 'Total Organic Phosphorus', 'Soil Physics', 'mmol kg-1', '土壤总有机磷储量', 'Total organic phosphorus pool in soil'),
            ('DOC', '土壤可溶性有机碳 (Dissolved Organic C)', 'Soil Dissolved Organic Carbon', 'Soil Physics', 'mg C kg-1', '可被微生物直接吸收利用的可溶性有机碳', 'Dissolved organic carbon readily bioavailable to microbes'),
            ('PH', '土壤酸碱度 (Soil pH)', 'Soil pH', 'Soil Physics', 'pH units', '土壤溶液氢离子活度指标', 'Soil reaction in water/CaCl2 suspension'),
            ('MAT', '年均温 (Mean Annual Temperature)', 'Mean Annual Temperature', 'Soil Physics', '°C', '采样点长周期气候年均温', 'Long-term mean annual air temperature'),
            ('MAP', '年降水量 (Mean Annual Precipitation)', 'Mean Annual Precipitation', 'Soil Physics', 'mm', '采样点长周期年均降水总量', 'Long-term mean annual precipitation sum'),
            ('TSOI', '土壤剖面温度 (Soil Temperature)', 'Soil Profile Temperature', 'Soil Physics', '°C', '采样层土壤热动力学状态观测', 'Layered soil profile thermal temperature'),

            # 气体通量 (Gas Fluxes)
            ('HR', '土壤异养呼吸 (Heterotrophic Respiration)', 'Heterotrophic Respiration', 'Gas Flux', 'g C m-2 d-1', '微生物有机质分解碳释放', 'Microbial heterotrophic decomposition carbon flux'),
            ('CH4_FLUX', '甲烷净通量 (CH4 Net Surface Flux)', 'Net Methane Surface Flux', 'Gas Flux', 'mg C m-2 d-1', '地表甲烷净排放通量', 'Net surface methane exchange flux')
        ]
        var_map = {}
        for code, dname, dname_en, cat, unit, desc, desc_en in default_variables:
            var_obj = VariableDefinition.query.filter_by(code=code).first()
            if not var_obj:
                var_obj = VariableDefinition(
                    code=code,
                    display_name=dname,
                    display_name_en=dname_en,
                    category=cat,
                    unit=unit,
                    description=desc,
                    description_en=desc_en
                )
                db.session.add(var_obj)
                db.session.flush()
            else:
                var_obj.display_name = dname
                var_obj.display_name_en = dname_en
                var_obj.category = cat
                var_obj.unit = unit
                var_obj.description = desc
                var_obj.description_en = desc_en
            var_map[code] = var_obj
        db.session.commit()

        # 2.2 初始预置全球生态样点/区域
        default_sites = [
            ('Global-Terrestrial', 'Global Terrestrial Ecosystems (全球陆地生态系统样点集)', 'Global', 20.0, 0.0, 300.0, 'Global / Multi-Biome'),
            ('US-Atq', 'Atqasuk Tundra Research Site (阿拉斯加北极苔原站)', 'United States', 70.47, -157.41, 15.0, 'Tundra'),
            ('US-Brw', 'Barrow Environmental Observatory (巴罗北极环境观测站)', 'United States', 71.32, -156.61, 4.0, 'Tundra'),
            ('US-SPR', 'SPRUCE Peatland (明尼苏达云杉泥炭湿地加热实验站)', 'United States', 47.50, -93.45, 418.0, 'Peatland/Boreal Bog'),
            ('CN-Sanjiang', '三江平原沼泽湿地生态试验站 (Sanjiang Wetland)', 'China', 47.58, 133.52, 55.0, 'Wetland'),
            ('SE-St1', 'Stordalen Mire (瑞典亚北极多年冻土泥炭沼泽站)', 'Sweden', 68.35, 19.05, 360.0, 'Peatland/Permafrost')
        ]
        site_map = {}
        for scode, sname, country, lat, lon, elev, biome in default_sites:
            s_obj = SiteLocation.query.filter_by(site_code=scode).first()
            if not s_obj:
                s_obj = SiteLocation(
                    site_code=scode,
                    site_name=sname,
                    country=country,
                    latitude=lat,
                    longitude=lon,
                    elevation=elev,
                    biome=biome
                )
                db.session.add(s_obj)
                db.session.flush()
            site_map[scode] = s_obj
        db.session.commit()

        # 3. 初始数据存储目录
        data_dir = os.path.join(app.config['UPLOAD_FOLDER'])
        os.makedirs(data_dir, exist_ok=True)

        # 4. 预置默认 OSS 配置样例
        if StorageConfig.query.count() == 0:
            default_oss = StorageConfig(
                provider='aliyun_oss',
                endpoint='oss-cn-beijing.aliyuncs.com',
                bucket_name='sdsu-microbial-data-bucket',
                access_key_id='LTAI5tDemoAccessKeyId2026',
                access_key_secret='DemoSecretAccessKeySecret987654321',
                custom_domain='https://data-cdn.sdsu-microbe.org',
                is_active=True
            )
            db.session.add(default_oss)
            db.session.commit()

        # 5. 预置真实 MicrobialDataSystem 数据集
        if Dataset.query.count() == 0:
            from datetime import date
            
            # 数据集 1: 全球土壤微生物量碳/氮/磷空间观测数据集 (真实 CSV 对应)
            ds1 = Dataset(
                title='Global Soil Microbial Biomass C/N/P Spatial Observation Dataset (全球土壤微生物量碳氮磷空间实测数据集)',
                year=2020,
                author='Xiaofeng Xu, P. E. Thornton, W. M. Post, et al. (SDSU & ORNL)',
                doi='10.1111/geb.12029',
                description='基于 email-clm/MicrobialDataSystem 仓库核心数据文件 Soil_Microbial_Biomass_C_N_P_spatial.csv。汇总全球各大生物群系（森林、草原、农田、苔原、荒漠）顶层及剖面土壤微生物量碳 (MBC)、氮 (MBN)、磷 (MBP)、有机碳 (SOC)、全氮 (TN) 及 pH 实测样点数据。',
                data_source_type='github',
                github_url='https://raw.githubusercontent.com/email-clm/MicrobialDataSystem/master/Soil_Microbial_Biomass_C_N_P_spatial.csv',
                local_file_path='Soil_Microbial_Biomass_C_N_P_spatial.csv',
                download_count=128,
                site_code='Global-Terrestrial',
                site=site_map.get('Global-Terrestrial'),
                spatial_scale='Global',
                start_date=date(1980, 1, 1),
                end_date=date(2020, 12, 31),
                temporal_resolution='Yearly',
                data_type='Field Observation',
                scenario='Control',
                min_depth=0.0,
                max_depth=1.0
            )
            ds1.keywords.extend([
                kw_map['soil_microbial_biomass'],
                kw_map['microbial_biomass_c'],
                kw_map['microbial_biomass_n'],
                kw_map['microbial_biomass_p'],
                kw_map['microbial_stoichiometry'],
                kw_map['soil_ph']
            ])
            ds1.variables.extend([
                var_map['MBC'],
                var_map['MBN'],
                var_map['MBP'],
                var_map['SOC'],
                var_map['TN'],
                var_map['PH'],
                var_map['MAT'],
                var_map['MAP']
            ])

            # 数据集 2: 全球土壤微生物生物量碳氮网格化模拟集 (对应 Global_Soil_Microbial_BiomassCN.nc)
            ds2 = Dataset(
                title='Global Soil Microbial Biomass Carbon & Nitrogen Gridded Dataset (全球土壤微生物生物量碳氮网格化模拟集)',
                year=2021,
                author='Xiaofeng Xu, D. Hui, A. W. King, et al. (SDSU & CAS)',
                doi='10.1038/srep17445',
                description='对应 email-clm/MicrobialDataSystem 仓库文件 Global_Soil_Microbial_BiomassCN.nc。包含全球 0.5° × 0.5° 空间网格分辨率下表层及底层土壤微生物碳氮生物地理分布、碳氮磷化学计量趋同性模拟矩阵。',
                data_source_type='github',
                github_url='https://raw.githubusercontent.com/email-clm/MicrobialDataSystem/master/Global_Soil_Microbial_BiomassCN.nc',
                local_file_path='Global_Soil_Microbial_BiomassCN.nc',
                download_count=92,
                site_code='Global-Terrestrial',
                site=site_map.get('Global-Terrestrial'),
                spatial_scale='Global',
                start_date=date(2000, 1, 1),
                end_date=date(2021, 12, 31),
                temporal_resolution='Monthly',
                data_type='Model Simulation',
                scenario='Control',
                min_depth=0.0,
                max_depth=1.5
            )
            ds2.keywords.extend([
                kw_map['soil_microbial_biomass'],
                kw_map['microbial_biomass_c'],
                kw_map['microbial_biomass_n'],
                kw_map['microbial_stoichiometry']
            ])
            ds2.variables.extend([
                var_map['MBC'],
                var_map['MBN'],
                var_map['SOC'],
                var_map['TN'],
                var_map['MAT'],
                var_map['MAP']
            ])

            # 数据集 3: 全球表层土壤真菌与细菌生物量碳生物地理学分布集
            ds3 = Dataset(
                title='Global Biogeography of Fungal and Bacterial Biomass Carbon in Topsoil (全球表层土壤真菌与细菌碳分布集)',
                year=2020,
                author='Liyuan He, J. L. M. Rodrigues, Xiaofeng Xu, et al. (Soil Biology & Biochemistry)',
                doi='10.1016/j.soilbio.2020.108024',
                description='集成全球各大经纬度生态系统表层土壤真菌生物量碳 (FBC) 与细菌生物量碳 (BBC) 实测数据，剖析真菌/细菌比例 (F:B ratio) 随环境温度、湿度与植被类型梯度的宏观空间分异特征。',
                data_source_type='github',
                github_url='https://github.com/email-clm/MicrobialDataSystem',
                local_file_path='Soil_Microbial_Biomass_C_N_P_spatial.csv',
                download_count=76,
                site_code='US-SPR',
                site=site_map.get('US-SPR'),
                spatial_scale='Global',
                start_date=date(2010, 1, 1),
                end_date=date(2020, 12, 31),
                temporal_resolution='Yearly',
                data_type='Hybrid',
                scenario='Control',
                min_depth=0.0,
                max_depth=0.2
            )
            ds3.keywords.extend([
                kw_map['fungal_biomass'],
                kw_map['bacterial_biomass'],
                kw_map['fungal_bacterial_ratio'],
                kw_map['forest_soil']
            ])
            ds3.variables.extend([
                var_map['FBC'],
                var_map['BBC'],
                var_map['SOC'],
                var_map['PH']
            ])

            # 数据集 4: 全球陆地生态系统土壤可溶性有机碳 (DOC) 储量与控制因素集
            ds4 = Dataset(
                title='Soil Dissolved Organic Carbon in Terrestrial Ecosystems (全球土壤可溶性有机碳DOC空间分布集)',
                year=2020,
                author='Ziyu Guo, Y. Wang, Liyuan He, Xiaofeng Xu, et al. (Global Ecology & Biogeography)',
                doi='10.1111/geb.13184',
                description='涵盖全球各大纬度带森林、草地、湿地及苔原土壤可溶性有机碳 (DOC) 空间格局与控制因素，探讨土壤微生物活动与水解产物对溶解性碳库的周转驱动机制。',
                data_source_type='oss',
                github_url=None,
                local_file_path='Soil_Microbial_Biomass_C_N_P_spatial.csv',
                download_count=45,
                site_code='CN-Sanjiang',
                site=site_map.get('CN-Sanjiang'),
                spatial_scale='Regional',
                start_date=date(2005, 1, 1),
                end_date=date(2020, 12, 31),
                temporal_resolution='Monthly',
                data_type='Field Observation',
                scenario='Control',
                min_depth=0.0,
                max_depth=1.0
            )
            ds4.keywords.extend([
                kw_map['soil_doc'],
                kw_map['soil_respiration'],
                kw_map['peatland_wetland']
            ])
            ds4.variables.extend([
                var_map['DOC'],
                var_map['SOC'],
                var_map['TN'],
                var_map['PH']
            ])

            # 数据集 5: 全球土壤微生物代谢商 (qCO2) 时合格局与微生态调控数据集
            ds5 = Dataset(
                title='Global Pattern and Controls of Soil Microbial Metabolic Quotient (qCO2) (全球土壤微生物代谢商格局集)',
                year=2017,
                author='Xiaofeng Xu, J. P. Schimel, I. A. Janssens, et al. (Ecological Monographs)',
                doi='10.1002/ecm.1258',
                description='记录单位土壤微生物量碳释放 CO2 的效率指标（代谢商 qCO2），揭示从热带到北极苔原在增温和养分胁迫下微生物群落碳利用效率 (CUE) 的生理生化适应机制。',
                data_source_type='github',
                github_url='https://github.com/email-clm/MicrobialDataSystem',
                local_file_path='Soil_Microbial_Biomass_C_N_P_spatial.csv',
                download_count=38,
                site_code='US-Atq',
                site=site_map.get('US-Atq'),
                spatial_scale='Global',
                start_date=date(2000, 1, 1),
                end_date=date(2017, 12, 31),
                temporal_resolution='Daily',
                data_type='Hybrid',
                scenario='Warming',
                min_depth=0.0,
                max_depth=0.5
            )
            ds5.keywords.extend([
                kw_map['metabolic_quotient'],
                kw_map['soil_respiration'],
                kw_map['soil_microbial_biomass'],
                kw_map['arctic_tundra']
            ])
            ds5.variables.extend([
                var_map['Q_MET'],
                var_map['MBC'],
                var_map['HR'],
                var_map['SOC'],
                var_map['TSOI']
            ])

            db.session.add_all([ds1, ds2, ds3, ds4, ds5])
            db.session.commit()

            # 插入审计日志
            log1 = DownloadLog(
                user_id=admin_user.id if admin_user else 1,
                dataset_id=ds1.id,
                download_type='github_redirect',
                ip_address='127.0.0.1',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X)',
                institution='SDSU Department of Biology',
                purpose='Model Calibration & Validation'
            )
            log2 = DownloadLog(
                user_id=researcher.id if researcher else 2,
                dataset_id=ds2.id,
                download_type='github_redirect',
                ip_address='127.0.0.1',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X)',
                institution='Northeast Institute of Geography and Agroecology, CAS',
                purpose='Academic Research'
            )
            log3 = DownloadLog(
                user_id=None,
                dataset_id=ds1.id,
                download_type='github_redirect',
                ip_address='192.168.1.102',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                institution='Oak Ridge National Laboratory',
                purpose='Teaching & Education'
            )
            db.session.add_all([log1, log2, log3])
            db.session.commit()

# ----------------- 路由逻辑 -----------------

@app.route('/')
def index():
    # 1. 基础全文检索 (标题、描述、作者、样点名称)
    query_str = request.args.get('q', '').strip()

    # 2. 时间跨度切片 (覆盖区间包含，StartA <= EndB and EndA >= StartB)
    start_year = request.args.get('start_year', type=int)
    end_year = request.args.get('end_year', type=int)
    temp_res = request.args.get('temp_res', '').strip()

    # 3. 空间与生态区维度
    selected_biomes = request.args.getlist('biome')
    selected_site = request.args.get('site', '').strip()
    spatial_scale = request.args.get('spatial_scale', '').strip()
    min_lat = request.args.get('min_lat', type=float)
    max_lat = request.args.get('max_lat', type=float)

    # 4. 指标变量多选 (要求数据集包含所选变量)
    selected_vars = request.args.getlist('var')

    # 5. 实验工况与数据类型
    data_type = request.args.get('data_type', '').strip()
    scenario = request.args.get('scenario', '').strip()

    # 6. 土层深度范围 (m)
    depth_max_filter = request.args.get('depth_max', type=float)

    # 7. 关键词快捷标引
    keyword_str = request.args.get('keyword', '').strip()

    # 构造动态查询
    query = Dataset.query.join(Dataset.site, isouter=True)

    if query_str:
        # 智能复合匹配：标题、描述、作者、样点名称、挂载变量代码、挂载关键词
        query = query.filter(
            (Dataset.title.ilike(f'%{query_str}%')) | 
            (Dataset.description.ilike(f'%{query_str}%')) |
            (Dataset.author.ilike(f'%{query_str}%')) |
            (SiteLocation.site_name.ilike(f'%{query_str}%')) |
            (SiteLocation.site_code.ilike(f'%{query_str}%')) |
            (Dataset.variables.any(VariableDefinition.code.ilike(f'%{query_str}%'))) |
            (Dataset.variables.any(VariableDefinition.display_name.ilike(f'%{query_str}%'))) |
            (Dataset.variables.any(VariableDefinition.display_name_en.ilike(f'%{query_str}%'))) |
            (Dataset.keywords.any(Keyword.name.ilike(f'%{query_str}%')))
        )

    # 时间跨度过滤
    if start_year:
        query = query.filter(
            (db.func.strftime('%Y', Dataset.end_date) >= str(start_year)) |
            (Dataset.year >= start_year)
        )
    if end_year:
        query = query.filter(
            (db.func.strftime('%Y', Dataset.start_date) <= str(end_year)) |
            (Dataset.year <= end_year)
        )
    if temp_res:
        query = query.filter(Dataset.temporal_resolution == temp_res)

    # 生态群系与样点
    if selected_biomes:
        query = query.filter(SiteLocation.biome.in_(selected_biomes))
    if selected_site:
        query = query.filter((SiteLocation.site_code == selected_site) | (Dataset.site_code == selected_site))
    if spatial_scale:
        query = query.filter(Dataset.spatial_scale == spatial_scale)
    if min_lat is not None and max_lat is not None:
        query = query.filter(SiteLocation.latitude.between(min_lat, max_lat))

    # 指标变量过滤 (交集匹配)
    if selected_vars:
        for v_code in selected_vars:
            query = query.filter(Dataset.variables.any(VariableDefinition.code == v_code))

    # 数据类型与情景
    if data_type:
        query = query.filter(Dataset.data_type == data_type)
    if scenario:
        query = query.filter(Dataset.scenario == scenario)

    # 垂直土层深度
    if depth_max_filter is not None:
        query = query.filter(Dataset.max_depth <= depth_max_filter)

    # 关键词
    if keyword_str:
        query = query.filter(Dataset.keywords.any(Keyword.name == keyword_str))

    datasets = query.order_by(Dataset.created_at.desc()).all()
    keywords = Keyword.query.order_by(Keyword.name.asc()).all()

    # 供给切片器的维度选项
    all_variables = VariableDefinition.query.order_by(VariableDefinition.category.asc(), VariableDefinition.code.asc()).all()
    all_biomes = [r[0] for r in db.session.query(SiteLocation.biome).distinct().filter(SiteLocation.biome != None).all()]
    all_sites = SiteLocation.query.order_by(SiteLocation.site_code.asc()).all()

    total_downloads = db.session.query(db.func.sum(Dataset.download_count)).scalar() or 0

    return render_template(
        'index.html',
        datasets=datasets,
        keywords=keywords,
        all_variables=all_variables,
        all_biomes=all_biomes,
        all_sites=all_sites,
        query=query_str,
        start_year=start_year,
        end_year=end_year,
        selected_biomes=selected_biomes,
        selected_site=selected_site,
        selected_vars=selected_vars,
        selected_data_type=data_type,
        selected_scenario=scenario,
        selected_kw=keyword_str,
        total_downloads=total_downloads
    )

@app.route('/dataset/<int:dataset_id>')
def detail(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    # 读取绑定的 CSV 文件解析给前端
    ts_file = os.path.join(app.config['UPLOAD_FOLDER'], dataset.local_file_path or 'Soil_Microbial_Biomass_C_N_P_spatial.csv')
    ts_data = parse_dataset_timeseries(ts_file)
    depth_data = get_depth_profile_data()
    kinetics_data = calculate_kinetics_curve()

    return render_template(
        'detail.html',
        dataset=dataset,
        ts_data=ts_data,
        depth_data=depth_data,
        kinetics_data=kinetics_data
    )

@app.route('/analysis')
def analysis():
    flash('交互式模型分析模块目前维护升级中，暂未开放访问', 'info')
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        year = request.form.get('year', '').strip()
        site_code = request.form.get('site_code', '').strip()
        site_id = request.form.get('site_id', type=int)
        spatial_scale = request.form.get('spatial_scale', 'Point')
        start_date_str = request.form.get('start_date', '').strip()
        end_date_str = request.form.get('end_date', '').strip()
        temporal_resolution = request.form.get('temporal_resolution', 'Daily')
        data_type = request.form.get('data_type', 'Model Simulation')
        scenario = request.form.get('scenario', 'Control')
        min_depth = request.form.get('min_depth', type=float) or 0.0
        max_depth = request.form.get('max_depth', type=float) or 1.0
        doi = request.form.get('doi', '').strip()
        description = request.form.get('description', '').strip()
        data_source_type = request.form.get('data_source_type', 'github')
        github_url = request.form.get('github_url', '').strip()
        keywords_str = request.form.get('keywords', '').strip()
        var_ids = request.form.getlist('variables')

        if not title or not author or not description:
            flash('请完整填写数据集标题、第一作者与摘要描述', 'error')
            return redirect(url_for('upload'))

        # 解析时间跨度日期
        from datetime import date
        s_date = None
        e_date = None
        try:
            if start_date_str:
                s_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            if end_date_str:
                e_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

        yr_val = int(year) if year.isdigit() else (s_date.year if s_date else 2023)
        if not s_date:
            s_date = date(yr_val, 1, 1)
        if not e_date:
            e_date = date(yr_val, 12, 31)

        # 处理文件或 GitHub / OSS 来源
        local_filename = None
        if data_source_type == 'oss':
            file = request.files.get('oss_file') or request.files.get('file')
            if file and file.filename:
                fname = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                file.save(save_path)
                local_filename = fname
                oss_key = f"datasets/{yr_val}/{fname}"
                upload_to_oss(save_path, oss_key)
            else:
                fname = f"sample_oss_{yr_val}.csv"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                generate_sample_clm_timeseries(save_path, year=yr_val)
                local_filename = fname
                upload_to_oss(save_path, f"datasets/{yr_val}/{fname}")
        elif data_source_type == 'local':
            file = request.files.get('file')
            if file and file.filename:
                fname = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                file.save(save_path)
                local_filename = fname
            else:
                fname = f"sample_{title[:8].strip().replace(' ', '_')}_{yr_val}.csv"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                generate_sample_clm_timeseries(save_path, year=yr_val)
                local_filename = fname
        else:
            local_filename = 'Soil_Microbial_Biomass_C_N_P_spatial.csv'

        target_site = None
        if site_id:
            target_site = db.session.get(SiteLocation, site_id)
        elif site_code:
            target_site = SiteLocation.query.filter_by(site_code=site_code).first()

        new_dataset = Dataset(
            title=title,
            author=author,
            year=yr_val,
            site=target_site,
            site_code=target_site.site_code if target_site else (site_code or 'US-Atq'),
            spatial_scale=spatial_scale,
            start_date=s_date,
            end_date=e_date,
            temporal_resolution=temporal_resolution,
            data_type=data_type,
            scenario=scenario,
            min_depth=min_depth,
            max_depth=max_depth,
            doi=doi,
            description=description,
            data_source_type=data_source_type,
            github_url=github_url if data_source_type == 'github' else None,
            local_file_path=local_filename,
            download_count=0
        )
        db.session.add(new_dataset)
        db.session.flush()

        # 关联多维变量指标 (支持已有勾选 + 动态手写录入新指标)
        if var_ids:
            for vid in var_ids:
                if str(vid).isdigit():
                    v_obj = db.session.get(VariableDefinition, int(vid))
                    if v_obj and v_obj not in new_dataset.variables:
                        new_dataset.variables.append(v_obj)

        new_custom_vars = request.form.get('custom_variables', '').strip()
        if new_custom_vars:
            # 格式例如: "MBC:mg C kg-1, MBN:mg N kg-1" 或 "PHOSPHATASE"
            raw_v_items = [v.strip() for v in new_custom_vars.replace('，', ',').split(',') if v.strip()]
            for item in raw_v_items:
                parts = item.split(':')
                v_code = parts[0].strip().upper()
                v_unit = parts[1].strip() if len(parts) > 1 else 'dimensionless'
                v_obj = VariableDefinition.query.filter_by(code=v_code).first()
                if not v_obj:
                    v_obj = VariableDefinition(
                        code=v_code,
                        display_name=f"{v_code} (User Added)",
                        display_name_en=f"{v_code} (User Added)",
                        category='Microbial Pool',
                        unit=v_unit,
                        description='User-defined microbial variable on upload',
                        description_en='User-defined microbial variable on upload'
                    )
                    db.session.add(v_obj)
                    db.session.flush()
                if v_obj not in new_dataset.variables:
                    new_dataset.variables.append(v_obj)

        # 关联关键词 (支持从已有词库挑选绑定 + 录入新词，自动纳管)
        selected_kw_ids = request.form.getlist('keyword_ids')
        if selected_kw_ids:
            for kid in selected_kw_ids:
                if str(kid).isdigit():
                    k_obj = db.session.get(Keyword, int(kid))
                    if k_obj and k_obj not in new_dataset.keywords:
                        new_dataset.keywords.append(k_obj)

        if keywords_str:
            raw_kws = [k.strip().lower() for k in keywords_str.replace('，', ',').split(',') if k.strip()]
            for k_name in raw_kws:
                kw_obj = Keyword.query.filter_by(name=k_name).first()
                if not kw_obj:
                    kw_obj = Keyword(name=k_name)
                    db.session.add(kw_obj)
                    db.session.flush()
                if kw_obj not in new_dataset.keywords:
                    new_dataset.keywords.append(kw_obj)

        db.session.commit()
        flash('科研数据集已成功录入，并已挂载时空与变量多维属性！', 'success')
        return redirect(url_for('detail', dataset_id=new_dataset.id))

    all_sites = SiteLocation.query.order_by(SiteLocation.site_code.asc()).all()
    all_variables = VariableDefinition.query.order_by(VariableDefinition.category.asc()).all()
    all_keywords = Keyword.query.order_by(Keyword.name.asc()).all()
    return render_template('upload.html', all_sites=all_sites, all_variables=all_variables, all_keywords=all_keywords)

# ----------------- 埋点下载与分发中转路由 -----------------
@app.route('/dataset/<int:dataset_id>/download', methods=['POST'])
def trigger_download(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    # 1. 获取前端填报的埋点审计信息
    data = request.get_json() or {}
    institution = data.get('institution', '未注明单位')
    purpose = data.get('purpose', 'Academic Research')

    # 2. 写入审计日志埋点表
    dl_type = 'github_redirect'
    if dataset.data_source_type == 'oss':
        dl_type = 'oss_download'
    elif dataset.data_source_type == 'local':
        dl_type = 'local_download'

    log = DownloadLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        dataset_id=dataset.id,
        download_type=dl_type,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:250] if request.user_agent else '',
        institution=institution,
        purpose=purpose
    )
    dataset.download_count += 1
    db.session.add(log)
    db.session.commit()

    # 3. 分发数据：支持 GitHub 仓库直连、OSS 云端分发 或 本地文件传输
    if dataset.data_source_type == 'github':
        # 如果配置了具体的 github_url 则优先使用，否则默认指向 MicrobialDataSystem 主仓库
        target_gh_url = dataset.github_url or 'https://github.com/email-clm/MicrobialDataSystem'
        return jsonify({'status': 'success', 'download_url': target_gh_url})
    elif dataset.data_source_type == 'oss':
        oss_key = f"datasets/{dataset.year}/{dataset.local_file_path or 'data.csv'}"
        oss_url = get_oss_download_url(oss_key)
        return jsonify({'status': 'success', 'download_url': oss_url or url_for('download_file', filename=dataset.local_file_path)})
    elif dataset.local_file_path:
        return jsonify({'status': 'success', 'download_url': url_for('download_file', filename=dataset.local_file_path)})
    else:
        return jsonify({'status': 'error', 'message': '目标数据源文件不存在'}), 404

@app.route('/files/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# ----------------- 认证系统 -----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if action == 'register':
            confirm_password = request.form.get('confirm_password', '').strip()
            email = request.form.get('email', '').strip()
            institution = request.form.get('institution', '').strip()

            current_lang = session.get('lang', 'zh')
            lang_dict = TRANSLATIONS.get(current_lang, TRANSLATIONS['zh'])

            if not username or not password or not email or not confirm_password:
                flash(lang_dict.get('form_email', '请完整填写注册信息'), 'error')
                return redirect(url_for('login'))

            if password != confirm_password:
                flash(lang_dict.get('password_mismatch', '两次输入的密码不一致，请重新输入'), 'error')
                return redirect(url_for('login'))

            if len(password) < 6:
                flash(lang_dict.get('password_too_weak', '密码强度不足，请至少设置6位字符'), 'error')
                return redirect(url_for('login'))

            if User.query.filter_by(username=username).first():
                msg = '用户名已存在，请换一个名称' if current_lang == 'zh' else 'Username already taken, please choose another.'
                flash(msg, 'error')
                return redirect(url_for('login'))
            
            user = User(username=username, email=email, institution=institution, role='user')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            succ_msg = '恭喜，科研账号注册成功并已自动登录！' if current_lang == 'zh' else 'Registration successful! You are now signed in.'
            flash(succ_msg, 'success')
            return redirect(url_for('index'))
        else:
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                succ_msg = f'欢迎回来，{user.username}！' if session.get('lang', 'zh') == 'zh' else f'Welcome back, {user.username}!'
                flash(succ_msg, 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            err_msg = '用户名或密码有误，请重新核对' if session.get('lang', 'zh') == 'zh' else 'Invalid username or password.'
            flash(err_msg, 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已安全退出当前会话', 'info')
    return redirect(url_for('index'))

# ----------------- 后台管理系统 -----------------
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('权限不足，仅管理员可访问后台埋点与管理系统', 'error')
        return redirect(url_for('index'))

    summary = get_dashboard_summary()
    return render_template('admin/dashboard.html', summary=summary)

# ----------------- 以数据为主数据的关键词管理 -----------------
@app.route('/dataset/<int:dataset_id>/keywords', methods=['POST'])
@login_required
def manage_dataset_keyword(dataset_id):
    if current_user.role != 'admin':
        flash('权限不足，仅管理员可维护关键词', 'error')
        return redirect(url_for('detail', dataset_id=dataset_id))

    dataset = Dataset.query.get_or_404(dataset_id)
    action = request.form.get('action')
    redirect_to = request.form.get('redirect_to', 'detail')

    if action == 'add':
        existing_kw_id = request.form.get('existing_keyword_id')
        new_kw_name = request.form.get('keyword_name', '').strip().lower()

        target_kw = None
        if existing_kw_id and existing_kw_id.isdigit():
            target_kw = db.session.get(Keyword, int(existing_kw_id))
        elif new_kw_name:
            target_kw = Keyword.query.filter_by(name=new_kw_name).first()
            if not target_kw:
                target_kw = Keyword(name=new_kw_name)
                db.session.add(target_kw)
                db.session.flush()

        if target_kw:
            if target_kw not in dataset.keywords:
                dataset.keywords.append(target_kw)
                db.session.commit()
                flash(f'已成功为数据集关联关键词 "#{target_kw.name}"', 'success')
            else:
                flash(f'该数据集已挂载过关键词 "#{target_kw.name}"', 'info')
        else:
            flash('请指定有效的新关键词或从已有词库选择', 'error')

    elif action == 'remove':
        kw_id = request.form.get('keyword_id')
        if kw_id and kw_id.isdigit():
            kw = db.session.get(Keyword, int(kw_id))
            if kw and kw in dataset.keywords:
                dataset.keywords.remove(kw)
                db.session.commit()
                flash(f'已解除数据集与关键词 "#{kw.name}" 的关联', 'info')

    if redirect_to == 'admin_keywords':
        return redirect(url_for('admin_keywords'))
    return redirect(url_for('detail', dataset_id=dataset.id))


@app.route('/admin/keywords', methods=['GET', 'POST'])
@login_required
def admin_keywords():
    if current_user.role != 'admin':
        flash('权限不足', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'cleanup_orphan':
            # 清理没有任何数据集关联的孤立关键词
            orphans = Keyword.query.filter(~Keyword.datasets.any()).all()
            count = len(orphans)
            for kw in orphans:
                db.session.delete(kw)
            db.session.commit()
            flash(f'已成功清理 {count} 个未关联任何数据集的孤立关键词', 'success')
            return redirect(url_for('admin_keywords'))

    datasets = Dataset.query.order_by(Dataset.created_at.desc()).all()
    all_keywords = Keyword.query.order_by(Keyword.name.asc()).all()
    return render_template('admin/keywords.html', datasets=datasets, all_keywords=all_keywords)

# ----------------- 后台 OSS 对象存储配置管理 -----------------
@app.route('/admin/oss', methods=['GET', 'POST'])
@login_required
def admin_oss():
    if current_user.role != 'admin':
        flash('权限不足，仅管理员可配置对象存储', 'error')
        return redirect(url_for('index'))

    oss_config = StorageConfig.query.first()

    if request.method == 'POST':
        provider = request.form.get('provider', 'aliyun_oss').strip()
        endpoint = request.form.get('endpoint', '').strip().replace('https://', '').replace('http://', '')
        bucket_name = request.form.get('bucket_name', '').strip()
        access_key_id = request.form.get('access_key_id', '').strip()
        access_key_secret = request.form.get('access_key_secret', '').strip()
        custom_domain = request.form.get('custom_domain', '').strip()
        is_active = bool(request.form.get('is_active'))

        if not endpoint or not bucket_name or not access_key_id or not access_key_secret:
            flash('请完整填写 OSS 地域节点、Bucket 及访问凭证', 'error')
            return redirect(url_for('admin_oss'))

        if not oss_config:
            oss_config = StorageConfig(
                provider=provider,
                endpoint=endpoint,
                bucket_name=bucket_name,
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                custom_domain=custom_domain,
                is_active=is_active
            )
            db.session.add(oss_config)
        else:
            oss_config.provider = provider
            oss_config.endpoint = endpoint
            oss_config.bucket_name = bucket_name
            oss_config.access_key_id = access_key_id
            oss_config.access_key_secret = access_key_secret
            oss_config.custom_domain = custom_domain
            oss_config.is_active = is_active

        db.session.commit()
        flash('OSS 对象存储配置已更新并成功启用！', 'success')
        return redirect(url_for('admin_oss'))

    return render_template('admin/oss.html', oss_config=oss_config)

# ----------------- 后台科研数据集综合管理 (CRUD) -----------------
@app.route('/admin/datasets')
@login_required
def admin_datasets():
    if current_user.role != 'admin':
        flash('权限不足，仅管理员可管理数据集', 'error')
        return redirect(url_for('index'))

    datasets = Dataset.query.order_by(Dataset.created_at.desc()).all()
    return render_template('admin/datasets.html', datasets=datasets)

@app.route('/admin/dataset/<int:dataset_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_dataset(dataset_id):
    if current_user.role != 'admin':
        flash('权限不足', 'error')
        return redirect(url_for('index'))

    dataset = Dataset.query.get_or_404(dataset_id)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        year = request.form.get('year', '').strip()
        site_id = request.form.get('site_id', type=int)
        site_code = request.form.get('site_code', '').strip()
        spatial_scale = request.form.get('spatial_scale', 'Point').strip()
        start_date_str = request.form.get('start_date', '').strip()
        end_date_str = request.form.get('end_date', '').strip()
        temporal_resolution = request.form.get('temporal_resolution', 'Daily').strip()
        data_type = request.form.get('data_type', 'Model Simulation').strip()
        scenario = request.form.get('scenario', 'Control').strip()
        min_depth = request.form.get('min_depth', type=float) or 0.0
        max_depth = request.form.get('max_depth', type=float) or 1.0
        doi = request.form.get('doi', '').strip()
        data_source_type = request.form.get('data_source_type', 'github').strip()
        github_url = request.form.get('github_url', '').strip()
        description = request.form.get('description', '').strip()

        if not title or not author or not description:
            flash('标题、作者及描述不能为空', 'error')
            return redirect(url_for('admin_edit_dataset', dataset_id=dataset.id))

        from datetime import date
        s_date = None
        e_date = None
        try:
            if start_date_str:
                s_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            if end_date_str:
                e_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except Exception:
            pass

        yr_val = int(year) if year.isdigit() else (s_date.year if s_date else dataset.year)

        target_site = None
        if site_id:
            target_site = db.session.get(SiteLocation, site_id)
        elif site_code:
            target_site = SiteLocation.query.filter_by(site_code=site_code).first()

        # 更新基本字段
        dataset.title = title
        dataset.author = author
        dataset.year = yr_val
        dataset.site = target_site
        dataset.site_code = target_site.site_code if target_site else (site_code or dataset.site_code)
        dataset.spatial_scale = spatial_scale
        if s_date:
            dataset.start_date = s_date
        if e_date:
            dataset.end_date = e_date
        dataset.temporal_resolution = temporal_resolution
        dataset.data_type = data_type
        dataset.scenario = scenario
        dataset.min_depth = min_depth
        dataset.max_depth = max_depth
        dataset.doi = doi
        dataset.data_source_type = data_source_type
        dataset.github_url = github_url if data_source_type == 'github' else None
        dataset.description = description

        # 重新挂载所选的标准化变量
        var_ids = request.form.getlist('variables')
        dataset.variables.clear()
        for vid in var_ids:
            if str(vid).isdigit():
                v_obj = db.session.get(VariableDefinition, int(vid))
                if v_obj and v_obj not in dataset.variables:
                    dataset.variables.append(v_obj)

        new_custom_vars = request.form.get('custom_variables', '').strip()
        if new_custom_vars:
            raw_v_items = [v.strip() for v in new_custom_vars.replace('，', ',').split(',') if v.strip()]
            for item in raw_v_items:
                parts = item.split(':')
                v_code = parts[0].strip().upper()
                v_unit = parts[1].strip() if len(parts) > 1 else 'dimensionless'
                v_obj = VariableDefinition.query.filter_by(code=v_code).first()
                if not v_obj:
                    v_obj = VariableDefinition(
                        code=v_code,
                        display_name=f"{v_code} (User Added)",
                        display_name_en=f"{v_code} (User Added)",
                        category='Microbial Pool',
                        unit=v_unit,
                        description='User-defined variable',
                        description_en='User-defined variable'
                    )
                    db.session.add(v_obj)
                    db.session.flush()
                if v_obj not in dataset.variables:
                    dataset.variables.append(v_obj)

        # 重新同步关联关键词
        kw_ids = request.form.getlist('keyword_ids')
        dataset.keywords.clear()
        for kid in kw_ids:
            if str(kid).isdigit():
                k_obj = db.session.get(Keyword, int(kid))
                if k_obj:
                    dataset.keywords.append(k_obj)

        # 追加新手写关键词
        extra_kws = request.form.get('keywords', '').strip()
        if extra_kws:
            raw_kws = [k.strip().lower() for k in extra_kws.replace('，', ',').split(',') if k.strip()]
            for k_name in raw_kws:
                kw_obj = Keyword.query.filter_by(name=k_name).first()
                if not kw_obj:
                    kw_obj = Keyword(name=k_name)
                    db.session.add(kw_obj)
                    db.session.flush()
                if kw_obj not in dataset.keywords:
                    dataset.keywords.append(kw_obj)

        db.session.commit()
        flash(f'数据集 #{dataset.id} 更新成功！', 'success')
        return redirect(url_for('admin_datasets'))

    all_sites = SiteLocation.query.order_by(SiteLocation.site_code.asc()).all()
    all_variables = VariableDefinition.query.order_by(VariableDefinition.category.asc()).all()
    all_keywords = Keyword.query.order_by(Keyword.name.asc()).all()
    return render_template('admin/dataset_edit.html', dataset=dataset, all_sites=all_sites, all_variables=all_variables, all_keywords=all_keywords)

@app.route('/admin/dataset/<int:dataset_id>/delete', methods=['POST'])
@login_required
def admin_delete_dataset(dataset_id):
    if current_user.role != 'admin':
        flash('权限不足', 'error')
        return redirect(url_for('index'))

    dataset = Dataset.query.get_or_404(dataset_id)
    ds_title = dataset.title

    # 清理关联的审计下载日志与关联多对多
    DownloadLog.query.filter_by(dataset_id=dataset.id).delete()
    dataset.keywords.clear()
    dataset.variables.clear()

    db.session.delete(dataset)
    db.session.commit()

    flash(f'数据集 #{dataset_id} "{ds_title[:20]}..." 已成功从系统中彻底删除！', 'info')
    return redirect(url_for('admin_datasets'))

# ----------------- 后台标准化观测指标字典管理 (CRUD) -----------------
@app.route('/admin/variables', methods=['GET', 'POST'])
@login_required
def admin_variables():
    if current_user.role != 'admin':
        flash('权限不足，仅管理员可维护指标字典', 'error')
        return redirect(url_for('index'))

    edit_id = request.args.get('edit_id', type=int)
    edit_var = db.session.get(VariableDefinition, edit_id) if edit_id else None

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create':
            code = request.form.get('code', '').strip().upper()
            display_name = request.form.get('display_name', '').strip()
            display_name_en = request.form.get('display_name_en', '').strip()
            category = request.form.get('category', 'Gas Flux').strip()
            unit = request.form.get('unit', '').strip()
            description = request.form.get('description', '').strip()
            description_en = request.form.get('description_en', '').strip()

            if not code or not display_name or not unit:
                flash('指标代码、显示名称与单位不能为空', 'error')
                return redirect(url_for('admin_variables'))

            if VariableDefinition.query.filter_by(code=code).first():
                flash(f'指标代码 "{code}" 已存在，请勿重复定义', 'error')
                return redirect(url_for('admin_variables'))

            new_v = VariableDefinition(
                code=code,
                display_name=display_name,
                display_name_en=display_name_en,
                category=category,
                unit=unit,
                description=description,
                description_en=description_en
            )
            db.session.add(new_v)
            db.session.commit()
            flash(f'科学指标 "{code}" 添加发布成功！', 'success')
            return redirect(url_for('admin_variables'))

        elif action == 'update':
            var_id = request.form.get('var_id', type=int)
            v_obj = db.session.get(VariableDefinition, var_id)
            if v_obj:
                v_obj.display_name = request.form.get('display_name', '').strip()
                v_obj.display_name_en = request.form.get('display_name_en', '').strip()
                v_obj.category = request.form.get('category', '').strip()
                v_obj.unit = request.form.get('unit', '').strip()
                v_obj.description = request.form.get('description', '').strip()
                v_obj.description_en = request.form.get('description_en', '').strip()
                db.session.commit()
                flash(f'指标 "{v_obj.code}" 信息已成功更新！', 'success')
            return redirect(url_for('admin_variables'))

    variables = VariableDefinition.query.order_by(VariableDefinition.category.asc(), VariableDefinition.code.asc()).all()
    return render_template('admin/variables.html', variables=variables, edit_var=edit_var)

@app.route('/admin/variable/<int:var_id>/delete', methods=['POST'])
@login_required
def admin_delete_variable(var_id):
    if current_user.role != 'admin':
        flash('权限不足', 'error')
        return redirect(url_for('index'))

    v_obj = db.session.get(VariableDefinition, var_id)
    if v_obj:
        v_code = v_obj.code
        db.session.delete(v_obj)
        db.session.commit()
        flash(f'科学指标 "{v_code}" 已从词典中删除', 'info')

    return redirect(url_for('admin_variables'))

if __name__ == '__main__':
    seed_database()
    app.run(host='0.0.0.0', port=5001, debug=True)

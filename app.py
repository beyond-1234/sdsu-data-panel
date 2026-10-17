import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config import Config
from models import db, User, Dataset, Keyword, DownloadLog
from services.data_parser import (
    generate_sample_clm_timeseries,
    parse_dataset_timeseries,
    get_depth_profile_data,
    calculate_kinetics_curve
)
from services.stats_service import get_dashboard_summary
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

        # 2. 初始预置关键词
        default_keywords = [
            'methanogenesis',
            'methanotrophy',
            'fungal_biomass',
            'bacterial_biomass',
            'soil_respiration',
            'arctic_tundra',
            'q10_temperature_sensitivity',
            'subsurface_permafrost'
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

        # 3. 初始生成模拟数据文件
        data_dir = os.path.join(app.config['UPLOAD_FOLDER'])
        os.makedirs(data_dir, exist_ok=True)

        sample_csv_1 = os.path.join(data_dir, 'clm_microbe_us_atq_2021.csv')
        if not os.path.exists(sample_csv_1):
            generate_sample_clm_timeseries(sample_csv_1, year=2021, site='US-Atq')

        sample_csv_2 = os.path.join(data_dir, 'clm_microbe_arctic_permafrost_2022.csv')
        if not os.path.exists(sample_csv_2):
            generate_sample_clm_timeseries(sample_csv_2, year=2022, site='US-Atq')

        # 4. 预置数据集记录
        if Dataset.query.count() == 0:
            ds1 = Dataset(
                title='CLM-Microbe 北极苔原 (US-Atq) 土壤异养呼吸与甲烷通量模拟驱动集',
                year=2021,
                author='SDSU Ecohydrology Lab / CLM-Microbe Working Group',
                doi='10.5281/zenodo.7891023',
                description='本数据集基于 CLM-Microbe 显式微生物机制模型，整合北极湿地苔原站点（US-Atq，Atqasuk）水热条件驱动与模拟输出。包含日尺度异养呼吸（HR）、细菌（BBC）与真菌（FBC）生物量以及地表甲烷净通量响应。',
                data_source_type='github',
                github_url='https://raw.githubusercontent.com/email-clm/clm-microbe/main/inputdata/atqasuk_forcing.csv',
                local_file_path='clm_microbe_us_atq_2021.csv',
                download_count=42,
                site_code='US-Atq'
            )
            ds1.keywords.extend([
                kw_map['methanogenesis'],
                kw_map['soil_respiration'],
                kw_map['arctic_tundra'],
                kw_map['fungal_biomass']
            ])

            ds2 = Dataset(
                title='多年冻土融化活动层多深度剖面微生物量碳与温敏系数 (Q10) 拟合集',
                year=2022,
                author='Zhang et al. (CAS & SDSU Joint Study)',
                doi='10.5281/zenodo.8239411',
                description='涵盖 0~1.5m 土壤分层深度下细菌生物量碳与真菌生物量碳实测与模式反演数据，提供不同底物浓度下的 Michaelis-Menten 反应动力学参数拟合结果。',
                data_source_type='local',
                github_url=None,
                local_file_path='clm_microbe_arctic_permafrost_2022.csv',
                download_count=28,
                site_code='US-Atq'
            )
            ds2.keywords.extend([
                kw_map['q10_temperature_sensitivity'],
                kw_map['bacterial_biomass'],
                kw_map['subsurface_permafrost'],
                kw_map['methanotrophy']
            ])

            ds3 = Dataset(
                title='全球 FLUXNET 苔原通量塔甲烷氧化与好氧呼吸机制模型验证集',
                year=2023,
                author='Global Tundra Ecology Network',
                doi='10.5281/zenodo.9012345',
                description='跨纬度苔原微生态通量交叉验证数据，面向陆面过程生物地球化学循环机制校准。',
                data_source_type='github',
                github_url='https://github.com/email-clm/clm-microbe/releases/tag/v1.0-data',
                local_file_path='clm_microbe_us_atq_2021.csv',
                download_count=19,
                site_code='Global-Tundra'
            )
            ds3.keywords.extend([
                kw_map['methanotrophy'],
                kw_map['soil_respiration'],
                kw_map['arctic_tundra']
            ])

            db.session.add_all([ds1, ds2, ds3])
            db.session.commit()

            # 插入一些初始模拟审计日志以支撑统计图表展示
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
                download_type='local_download',
                ip_address='127.0.0.1',
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X)',
                institution='CAS Institute of Geographic Sciences',
                purpose='Academic Research'
            )
            log3 = DownloadLog(
                user_id=None,
                dataset_id=ds1.id,
                download_type='github_redirect',
                ip_address='192.168.1.102',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                institution='University of Alaska Fairbanks',
                purpose='Teaching & Education'
            )
            db.session.add_all([log1, log2, log3])
            db.session.commit()

# ----------------- 路由逻辑 -----------------

@app.route('/')
def index():
    query_str = request.args.get('q', '').strip()
    year_str = request.args.get('year', '').strip()
    keyword_str = request.args.get('keyword', '').strip()

    query = Dataset.query

    if query_str:
        query = query.filter(
            (Dataset.title.ilike(f'%{query_str}%')) | 
            (Dataset.description.ilike(f'%{query_str}%')) |
            (Dataset.author.ilike(f'%{query_str}%'))
        )
    if year_str and year_str.isdigit():
        query = query.filter(Dataset.year == int(year_str))
    if keyword_str:
        query = query.join(Dataset.keywords).filter(Keyword.name == keyword_str)

    datasets = query.order_by(Dataset.created_at.desc()).all()
    keywords = Keyword.query.order_by(Keyword.name.asc()).all()
    
    # 全部可选年份
    all_years = [r[0] for r in db.session.query(Dataset.year).distinct().order_by(Dataset.year.desc()).all()]
    total_downloads = db.session.query(db.func.sum(Dataset.download_count)).scalar() or 0

    return render_template(
        'index.html',
        datasets=datasets,
        keywords=keywords,
        available_years=all_years,
        query=query_str,
        selected_year=year_str,
        selected_kw=keyword_str,
        total_downloads=total_downloads
    )

@app.route('/dataset/<int:dataset_id>')
def detail(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    # 读取绑定的 CSV 文件解析给前端
    ts_file = os.path.join(app.config['UPLOAD_FOLDER'], dataset.local_file_path or 'clm_microbe_us_atq_2021.csv')
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
    depth_data = get_depth_profile_data()
    return render_template('analysis.html', depth_data=depth_data)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        author = request.form.get('author', '').strip()
        year = request.form.get('year', '').strip()
        site_code = request.form.get('site_code', '').strip()
        doi = request.form.get('doi', '').strip()
        description = request.form.get('description', '').strip()
        data_source_type = request.form.get('data_source_type', 'github')
        github_url = request.form.get('github_url', '').strip()
        keywords_str = request.form.get('keywords', '').strip()

        if not title or not author or not year or not description:
            flash('请完整填写数据集标题、第一作者、年份与摘要描述', 'error')
            return redirect(url_for('upload'))

        # 处理文件或 GitHub 来源
        local_filename = None
        if data_source_type == 'local':
            file = request.files.get('file')
            if file and file.filename:
                fname = secure_filename(file.filename)
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                file.save(save_path)
                local_filename = fname
            else:
                # 默认生成一份样本时序支撑可视化
                fname = f"sample_{title[:8].strip().replace(' ', '_')}_{year}.csv"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                generate_sample_clm_timeseries(save_path, year=int(year) if year.isdigit() else 2022)
                local_filename = fname
        else:
            # GitHub 类型同样绑定一份样点预览
            local_filename = 'clm_microbe_us_atq_2021.csv'

        new_dataset = Dataset(
            title=title,
            author=author,
            year=int(year) if year.isdigit() else 2023,
            site_code=site_code or 'US-Atq',
            doi=doi,
            description=description,
            data_source_type=data_source_type,
            github_url=github_url if data_source_type == 'github' else None,
            local_file_path=local_filename,
            download_count=0
        )

        # 关联关键词
        if keywords_str:
            raw_kws = [k.strip().lower() for k in keywords_str.replace('，', ',').split(',') if k.strip()]
            for k_name in raw_kws:
                kw_obj = Keyword.query.filter_by(name=k_name).first()
                if not kw_obj:
                    kw_obj = Keyword(name=k_name)
                    db.session.add(kw_obj)
                    db.session.flush()
                new_dataset.keywords.append(kw_obj)

        db.session.add(new_dataset)
        db.session.commit()
        flash('数据集已成功提交并归档纳管！', 'success')
        return redirect(url_for('detail', dataset_id=new_dataset.id))

    return render_template('upload.html')

# ----------------- 埋点下载与分发中转路由 -----------------
@app.route('/dataset/<int:dataset_id>/download', methods=['POST'])
def trigger_download(dataset_id):
    dataset = Dataset.query.get_or_404(dataset_id)
    
    # 1. 获取前端填报的埋点审计信息
    data = request.get_json() or {}
    institution = data.get('institution', '未注明单位')
    purpose = data.get('purpose', 'Academic Research')

    # 2. 写入审计日志埋点表
    log = DownloadLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        dataset_id=dataset.id,
        download_type='github_redirect' if dataset.data_source_type == 'github' else 'local_download',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:250] if request.user_agent else '',
        institution=institution,
        purpose=purpose
    )
    dataset.download_count += 1
    db.session.add(log)
    db.session.commit()

    # 3. 分发数据：支持 GitHub 直链重定向 或 本地文件传输
    if dataset.data_source_type == 'github' and dataset.github_url:
        return jsonify({'status': 'success', 'download_url': dataset.github_url})
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

if __name__ == '__main__':
    seed_database()
    app.run(host='0.0.0.0', port=5001, debug=True)

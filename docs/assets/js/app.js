/* =========================================================================
   MicrobialDataSystem - Static GitHub Pages Application
   Pure client-side rendering of the archived dataset catalogue.
   Data source: assets/js/data.js (exported from the Flask database).
   ========================================================================= */

(function () {
    'use strict';

    var DATA = window.PORTAL_DATA || { datasets: [], variables: [], keywords: [], sites: [] };
    var GITHUB_REPO_URL = 'https://github.com/email-clm/MicrobialDataSystem';

    var state = {
        query: '',
        startYear: '',
        endYear: '',
        siteCode: '',
        dataType: '',
        biomes: {},
        variables: {},
        tagsExpanded: false
    };

    var charts = [];

    /* ---------------------------------------------------------------- utils */

    function esc(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function safeCell(value) {
        if (value === null || value === undefined || value === '' ||
            (typeof value === 'number' && isNaN(value))) {
            return '-';
        }
        return esc(value);
    }

    function rawFileUrl(ds) {
        if (ds.github_url) return ds.github_url;
        return 'https://raw.githubusercontent.com/email-clm/MicrobialDataSystem/master/' +
            encodeURIComponent(ds.local_file_path || '');
    }

    function showToast(message) {
        var toast = document.getElementById('appToast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'appToast';
            toast.style.cssText =
                'position:fixed;right:24px;bottom:24px;z-index:9999;max-width:420px;' +
                'background:#1e293b;color:#fff;padding:14px 18px;border-radius:8px;' +
                'box-shadow:0 10px 30px rgba(0,0,0,0.25);font-size:0.88rem;line-height:1.5;' +
                'opacity:0;transition:opacity 0.25s ease;';
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.style.opacity = '1';
        clearTimeout(toast._timer);
        toast._timer = setTimeout(function () {
            toast.style.opacity = '0';
        }, 4200);
    }

    function scrollTop() {
        window.scrollTo({ top: 0, behavior: 'auto' });
    }

    /* --------------------------------------------------------------- router */

    function currentRoute() {
        var hash = window.location.hash || '#/';
        if (hash.indexOf('#/dataset/') === 0) {
            return { name: 'detail', id: parseInt(hash.replace('#/dataset/', ''), 10) };
        }
        return { name: 'home' };
    }

    function setActiveNav(name) {
        var el = document.getElementById('navOverview');
        if (el) el.classList.toggle('active', name === 'home' || name === 'detail');
    }

    function setBreadcrumb(parts) {
        var host = document.getElementById('headerBreadcrumbs');
        if (!host) return;
        var html = '<a href="#/">MicrobialData</a>';
        parts.forEach(function (part) {
            html += ' <span style="color:#94a3b8;margin:0 2px;">/</span> ';
            if (part.href) {
                html += '<a href="' + part.href + '">' + esc(part.label) + '</a>';
            } else {
                html += '<span>' + esc(part.label) + '</span>';
            }
        });
        host.innerHTML = html;
    }

    function showView(name) {
        ['viewHome', 'viewDetail'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.classList.toggle('active', id === 'view' + name.charAt(0).toUpperCase() + name.slice(1));
        });
    }

    function renderRoute() {
        var route = currentRoute();
        disposeCharts();

        if (route.name === 'detail') {
            var ds = DATA.datasets.filter(function (d) { return d.id === route.id; })[0];
            if (!ds) {
                showView('home');
                setActiveNav('home');
                showToast('Dataset not found in this static archive.');
                return;
            }
            showView('detail');
            setActiveNav('home');
            setBreadcrumb([
                { label: 'Data Discovery & Slicer', href: '#/' },
                { label: ds.title.length > 48 ? ds.title.slice(0, 48) + '...' : ds.title }
            ]);
            renderDetail(ds);
            scrollTop();
            return;
        }

        showView('home');
        setActiveNav('home');
        setBreadcrumb([{ label: 'Data Discovery & Slicer' }]);
        scrollTop();
    }

    /* ----------------------------------------------------------- home view */

    function datasetBiomes(ds) {
        var list = [];
        if (ds.site && ds.site.biome) list.push(ds.site.biome);
        var vis = ds.vis_data;
        if (vis && vis.data_type === 'csv' && vis.x_labels) {
            vis.x_labels.forEach(function (label) {
                if (label && list.indexOf(label) === -1) list.push(label);
            });
        }
        return list;
    }

    function isGlobalCoverage(ds) {
        var biome = (ds.site && ds.site.biome) || '';
        return /global|multi/i.test(biome);
    }

    function collectBiomes() {
        var all = [];
        DATA.datasets.forEach(function (ds) {
            datasetBiomes(ds).forEach(function (biome) {
                if (all.indexOf(biome) === -1) all.push(biome);
            });
        });
        return all.sort();
    }

    function populateFilters() {
        // Site filter: only sites actually referenced by archived datasets.
        var siteSelect = document.getElementById('filterSite');
        if (siteSelect) {
            var seen = {};
            var options = ['<option value="">All Sites</option>'];
            DATA.datasets.forEach(function (ds) {
                if (!ds.site_code || seen[ds.site_code]) return;
                seen[ds.site_code] = true;
                var label = ds.site_code;
                if (ds.site && ds.site.site_name) label += ' - ' + ds.site.site_name;
                options.push('<option value="' + esc(ds.site_code) + '">' + esc(label) + '</option>');
            });
            siteSelect.innerHTML = options.join('');
        }

        // Biome checklist: real biome labels observed in the archived files.
        var biomeHost = document.getElementById('biomeChecklist');
        if (biomeHost) {
            var biomes = collectBiomes();
            biomeHost.innerHTML = biomes.map(function (biome, index) {
                var id = 'biome_' + index;
                return '<label for="' + id + '" style="display:inline-flex;align-items:center;gap:6px;' +
                    'font-size:0.85rem;color:#334155;cursor:pointer;background:#f8fafc;' +
                    'border:1px solid var(--border-color);border-radius:14px;padding:4px 10px;">' +
                    '<input type="checkbox" id="' + id + '" data-biome="' + esc(biome) + '" ' +
                    'onchange="App.toggleBiome(this)"> ' + esc(biome) + '</label>';
            }).join('');
        }

        // Variable groups by category.
        var groups = {
            'Microbial Pool': 'varsMicrobial',
            'Soil Physics': 'varsPhysics',
            'Gas Flux': 'varsGas'
        };
        Object.keys(groups).forEach(function (category) {
            var host = document.getElementById(groups[category]);
            if (!host) return;
            var items = DATA.variables.filter(function (v) { return v.category === category; });
            if (!items.length) {
                host.innerHTML = '<span style="font-size:0.8rem;color:#94a3b8;">No archived variables in this category.</span>';
                return;
            }
            host.innerHTML = items.map(function (v, index) {
                var id = 'var_' + category.replace(/\s+/g, '_') + '_' + index;
                return '<label for="' + id + '" style="display:flex;align-items:center;gap:8px;' +
                    'font-size:0.84rem;color:#334155;cursor:pointer;">' +
                    '<input type="checkbox" id="' + id + '" data-code="' + esc(v.code) + '" ' +
                    'onchange="App.toggleVariable(this)">' +
                    '<strong>' + esc(v.code) + '</strong>' +
                    '<span style="color:#64748b;">' + esc(v.display_name_en || v.display_name) + '</span>' +
                    '<span style="color:var(--primary);font-size:0.76rem;">[' + esc(v.unit) + ']</span>' +
                    '</label>';
            }).join('');
        });

        // Key tags: top 6 with a collapsible remainder.
        renderKeyTags();
    }

    function renderKeyTags() {
        var host = document.getElementById('keyTagsContainer');
        if (!host) return;
        var tags = DATA.keywords.slice();
        var limit = state.tagsExpanded ? tags.length : 6;
        var html = tags.slice(0, limit).map(function (tag) {
            return '<a href="javascript:void(0);" class="badge" onclick="App.applyKeyword(\'' +
                esc(tag).replace(/'/g, "\\'") + '\')"># ' + esc(tag) + '</a>';
        }).join('');
        if (tags.length > 6) {
            html += '<button type="button" class="btn btn-outline btn-sm" onclick="App.toggleTags()" ' +
                'style="padding:2px 8px;font-size:0.75rem;border-radius:12px;color:var(--primary);border-color:#cbd5e1;">' +
                (state.tagsExpanded ? 'Show Less &#9650;' : 'More Tags (' + (tags.length - 6) + ') &#9660;') +
                '</button>';
        }
        host.innerHTML = html;
    }

    function matchesFilters(ds) {
        var q = state.query.trim().toLowerCase();
        if (q) {
            var haystack = [
                ds.title, ds.description, ds.author, ds.site_code, ds.data_type,
                ds.spatial_scale, ds.scenario, ds.year, ds.doi,
                ds.site ? ds.site.site_name : '',
                ds.site ? ds.site.biome : ''
            ].concat(ds.keywords || [])
                .concat((ds.variables || []).map(function (v) {
                    return v.code + ' ' + (v.display_name_en || v.display_name);
                }))
                .join(' ').toLowerCase();
            if (haystack.indexOf(q) === -1) return false;
        }

        var startYear = parseInt(state.startYear, 10);
        var endYear = parseInt(state.endYear, 10);
        if (!isNaN(startYear) || !isNaN(endYear)) {
            var dsStart = parseInt((ds.start_date || '').slice(0, 4), 10) || ds.year;
            var dsEnd = parseInt((ds.end_date || '').slice(0, 4), 10) || ds.year;
            if (!isNaN(startYear) && dsEnd < startYear) return false;
            if (!isNaN(endYear) && dsStart > endYear) return false;
        }

        if (state.siteCode && ds.site_code !== state.siteCode) return false;
        if (state.dataType && ds.data_type !== state.dataType) return false;

        var selectedBiomes = Object.keys(state.biomes).filter(function (k) { return state.biomes[k]; });
        if (selectedBiomes.length && !isGlobalCoverage(ds)) {
            var owned = datasetBiomes(ds);
            var hit = selectedBiomes.some(function (biome) { return owned.indexOf(biome) !== -1; });
            if (!hit) return false;
        }

        var selectedVars = Object.keys(state.variables).filter(function (k) { return state.variables[k]; });
        if (selectedVars.length) {
            var codes = (ds.variables || []).map(function (v) { return v.code; });
            var missing = selectedVars.some(function (code) { return codes.indexOf(code) === -1; });
            if (missing) return false;
        }

        return true;
    }

    function renderDatasetCards() {
        var host = document.getElementById('datasetCardsContainer');
        if (!host) return;
        var matched = DATA.datasets.filter(matchesFilters);

        var countBtn = document.getElementById('btnFilterCount');
        if (countBtn) {
            countBtn.textContent = 'Filter Datasets (' + matched.length + ')';
        }

        if (!matched.length) {
            host.innerHTML =
                '<div class="card" style="text-align:center;padding:48px 24px;color:var(--text-muted);">' +
                '<div style="font-size:2rem;margin-bottom:12px;">📊</div>' +
                '<div style="font-size:1.1rem;font-weight:500;">No datasets match the current slicer.</div>' +
                '<p style="margin-top:8px;font-size:0.88rem;">Relax one or more spatial, temporal, or variable constraints.</p>' +
                '<div style="margin-top:18px;"><button type="button" class="btn btn-outline btn-sm" ' +
                'onclick="App.resetFilters()">Reset Filters</button></div></div>';
            return;
        }

        host.innerHTML = matched.map(function (ds) {
            var coverage = (ds.start_date && ds.end_date)
                ? ds.start_date + ' ~ ' + ds.end_date
                : String(ds.year);

            var variables = (ds.variables || []).map(function (v) {
                return '<span class="badge" style="background:#f1f5f9;color:#1e293b;border:1px solid #cbd5e1;' +
                    'font-size:0.75rem;" title="' + esc(v.display_name_en || v.display_name) + '">' +
                    '<strong>' + esc(v.code) + '</strong> <small style="color:#64748b;">(' + esc(v.unit) + ')</small></span>';
            }).join(' ');

            var keywords = (ds.keywords || []).map(function (tag) {
                return '<a href="javascript:void(0);" class="badge" onclick="App.applyKeyword(\'' +
                    esc(tag).replace(/'/g, "\\'") + '\')"># ' + esc(tag) + '</a>';
            }).join(' ');

            var siteLine = ds.site
                ? esc(ds.site.site_code) + ' · ' + esc(ds.site.biome)
                : esc(ds.site_code || 'Global-Terrestrial');

            return '<div class="card" style="margin-bottom:0;transition:transform 0.2s,box-shadow 0.2s;" ' +
                'onmouseover="this.style.boxShadow=\'0 6px 18px rgba(0,0,0,0.08)\'" ' +
                'onmouseout="this.style.boxShadow=\'0 3px 12px rgba(0,0,0,0.04)\'">' +
                '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;">' +
                '<div style="flex:1;min-width:320px;">' +
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">' +
                '<span class="badge badge-primary">' + esc(ds.data_type) + '</span>' +
                '<span class="badge badge-brown">' + esc(ds.spatial_scale || 'Global') + '</span>' +
                (ds.scenario ? '<span class="badge" style="background:#fef3c7;color:#92400e;">Scenario: ' + esc(ds.scenario) + '</span>' : '') +
                '<span style="font-size:0.82rem;color:var(--text-muted);">Author <strong>' + esc(ds.author) + '</strong></span>' +
                '</div>' +
                '<h2 style="font-family:var(--font-serif);font-size:1.25rem;margin-bottom:12px;color:#1a202c;">' +
                '<a href="#/dataset/' + ds.id + '" style="text-decoration:none;color:inherit;">' + esc(ds.title) + '</a></h2>' +
                '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;' +
                'background:#f8fafc;border:1px solid var(--border-color);border-radius:6px;' +
                'padding:10px 14px;margin-bottom:14px;font-size:0.82rem;">' +
                '<div><span style="color:#64748b;">Coverage</span> <strong style="color:#1e293b;">' +
                esc(coverage) + '</strong> <span style="color:#94a3b8;">(' + esc(ds.temporal_resolution || 'Yearly') + ')</span></div>' +
                '<div><span style="color:#64748b;">Site / Biome</span> <strong style="color:#1e293b;">' + siteLine + '</strong></div>' +
                '<div><span style="color:#64748b;">Depth</span> <strong style="color:#1e293b;">' +
                esc(ds.min_depth || 0) + 'm ~ ' + esc(ds.max_depth || 1) + 'm</strong></div>' +
                '</div>' +
                '<p style="font-size:0.88rem;color:#4a5568;line-height:1.5;margin-bottom:12px;">' +
                esc(ds.description.length > 260 ? ds.description.slice(0, 260) + '...' : ds.description) + '</p>' +
                (variables ? '<div style="margin-bottom:10px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">' +
                    '<span style="font-size:0.78rem;font-weight:600;color:#475569;">Variables contained:</span> ' +
                    variables + '</div>' : '') +
                '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">' + keywords + '</div>' +
                '</div>' +
                '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:10px;min-width:170px;">' +
                '<div style="font-size:0.78rem;color:#718096;">Channel <span style="color:#0366d6;">' +
                esc(ds.data_source_type === 'github' ? 'GitHub Mirror' : (ds.data_source_type === 'oss' ? 'OSS Channel' : 'Local Archive')) +
                '</span></div>' +
                '<div style="display:flex;gap:8px;margin-top:8px;">' +
                '<a href="#/dataset/' + ds.id + '" class="btn btn-outline btn-sm">Preview</a>' +
                '<a href="' + esc(rawFileUrl(ds)) + '" target="_blank" rel="noopener" class="btn btn-primary btn-sm">Download</a>' +
                '</div></div></div></div>';
        }).join('');
    }

    function applySlicerFilters() {
        var qEl = document.getElementById('searchQuery');
        var startEl = document.getElementById('filterStartYear');
        var endEl = document.getElementById('filterEndYear');
        var siteEl = document.getElementById('filterSite');
        var typeEl = document.getElementById('filterDataType');

        state.query = qEl ? qEl.value : '';
        state.startYear = startEl ? startEl.value : '';
        state.endYear = endEl ? endEl.value : '';
        state.siteCode = siteEl ? siteEl.value : '';
        state.dataType = typeEl ? typeEl.value : '';
        renderDatasetCards();
    }

    function resetFilters() {
        state.query = '';
        state.startYear = '';
        state.endYear = '';
        state.siteCode = '';
        state.dataType = '';
        state.biomes = {};
        state.variables = {};

        ['searchQuery', 'filterStartYear', 'filterEndYear', 'filterSite', 'filterDataType'].forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) return;
            if (el.tagName === 'SELECT') el.selectedIndex = 0;
            else el.value = '';
        });
        document.querySelectorAll('#biomeChecklist input[type="checkbox"], ' +
            '#varsMicrobial input[type="checkbox"], #varsPhysics input[type="checkbox"], ' +
            '#varsGas input[type="checkbox"]').forEach(function (box) {
            box.checked = false;
        });
        renderDatasetCards();
    }

    /* --------------------------------------------------------- detail view */

    function renderDetail(ds) {
        var host = document.getElementById('detailContent');
        if (!host) return;

        var vis = ds.vis_data || null;

        var variables = (ds.variables || []).map(function (v) {
            return '<span class="badge" style="padding:6px 10px;background:#f1f5f9;color:#1e293b;' +
                'border:1px solid #cbd5e1;font-size:0.8rem;"><strong>' + esc(v.code) + '</strong> - ' +
                esc(v.display_name_en || v.display_name) +
                ' <span style="color:var(--primary);font-weight:bold;margin-left:4px;">[' + esc(v.unit) + ']</span></span>';
        }).join(' ');

        var keywords = (ds.keywords || []).map(function (tag) {
            return '<a href="javascript:void(0);" class="badge" onclick="App.applyKeyword(\'' +
                esc(tag).replace(/'/g, "\\'") + '\')"># ' + esc(tag) + '</a>';
        }).join(' ');

        var coverage = (ds.start_date && ds.end_date)
            ? ds.start_date + ' ~ ' + ds.end_date
            : String(ds.year);

        var siteLine = ds.site
            ? esc(ds.site.site_code) + ' (' + esc(ds.site.latitude) + '&#176;N, ' + esc(ds.site.longitude) + '&#176;E)'
            : esc(ds.site_code || 'Global-Terrestrial');
        var biomeLine = ds.site ? esc(ds.site.biome) : 'Terrestrial Ecosystem';

        host.innerHTML =
            '<div class="card">' +
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;">' +
            '<div style="flex:1;min-width:320px;">' +
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap;">' +
            '<span class="badge badge-primary">' + esc(ds.year) + '</span>' +
            (ds.site_code ? '<span class="badge badge-brown">Site ' + esc(ds.site_code) + '</span>' : '') +
            '<span class="badge">Source ' + esc((ds.data_source_type || 'local').toUpperCase()) + '</span>' +
            '</div>' +
            '<h1 style="font-family:var(--font-serif);font-size:1.6rem;margin-bottom:12px;color:#1a202c;">' +
            esc(ds.title) + '</h1>' +
            '<div style="font-size:0.88rem;color:var(--text-muted);margin-bottom:14px;">' +
            'Lead Author <strong style="color:var(--text-dark);">' + esc(ds.author) + '</strong>' +
            (ds.doi ? ' | DOI: <a href="https://doi.org/' + esc(ds.doi) + '" target="_blank" rel="noopener" ' +
                'style="color:var(--primary);">' + esc(ds.doi) + '</a>' : '') +
            '</div></div>' +
            '<div style="text-align:right;min-width:200px;">' +
            '<a href="' + esc(rawFileUrl(ds)) + '" target="_blank" rel="noopener" ' +
            'class="btn btn-primary" style="width:100%;">Download Dataset</a>' +
            (ds.github_url ? '<div style="margin-top:8px;font-size:0.75rem;">' +
                '<a href="' + GITHUB_REPO_URL + '" target="_blank" rel="noopener" style="color:#64748b;text-decoration:none;">' +
                'View GitHub Repository</a></div>' : '') +
            '</div></div>' +

            '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;' +
            'background:#f8fafc;border:1px solid var(--border-color);border-radius:8px;' +
            'padding:14px 18px;margin-top:14px;font-size:0.88rem;">' +
            '<div><div style="font-size:0.75rem;text-transform:uppercase;color:#64748b;font-weight:600;">Temporal Coverage</div>' +
            '<strong style="color:#1e293b;">' + esc(coverage) + '</strong> ' +
            '<span style="color:#94a3b8;font-size:0.8rem;">(' + esc(ds.temporal_resolution || 'Yearly') + ')</span></div>' +
            '<div><div style="font-size:0.75rem;text-transform:uppercase;color:#64748b;font-weight:600;">Site &amp; Biome</div>' +
            '<strong style="color:#1e293b;">' + siteLine + '</strong>' +
            '<div style="color:#64748b;font-size:0.8rem;">' + biomeLine + '</div></div>' +
            '<div><div style="font-size:0.75rem;text-transform:uppercase;color:#64748b;font-weight:600;">Depth Range</div>' +
            '<strong style="color:#1e293b;">' + esc(ds.min_depth || 0) + 'm ~ ' + esc(ds.max_depth || 1) + 'm</strong>' +
            '<div style="color:#64748b;font-size:0.8rem;">Soil profile coverage of the archived observations</div></div>' +
            '<div><div style="font-size:0.75rem;text-transform:uppercase;color:#64748b;font-weight:600;">Scenario</div>' +
            '<strong style="color:#1e293b;">' + esc(ds.data_type) + '</strong>' +
            '<div style="color:#64748b;font-size:0.8rem;">Treatment: ' + esc(ds.scenario || 'Control') + '</div></div>' +
            '</div>' +

            (variables ? '<div style="margin-top:14px;padding:12px 16px;background:#fff;' +
                'border:1px solid var(--border-color);border-radius:8px;">' +
                '<div style="font-size:0.8rem;font-weight:bold;color:#475569;margin-bottom:8px;">Managed Variables</div>' +
                '<div style="display:flex;gap:8px;flex-wrap:wrap;">' + variables + '</div></div>' : '') +

            '<div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border-color);' +
            'line-height:1.65;color:#374151;">' +
            '<h3 style="font-family:var(--font-serif);font-size:1.05rem;margin-bottom:8px;">Abstract</h3>' +
            '<p>' + esc(ds.description) + '</p></div>' +

            '<div style="margin-top:16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
            '<span style="font-size:0.82rem;color:var(--text-muted);font-weight:600;">Tags</span>' +
            keywords + '</div></div>' +

            (vis ? renderDetailCharts(vis) : '');

        if (vis) {
            requestAnimationFrame(function () { initDetailCharts(vis); });
        }
    }

    function renderDetailCharts(vis) {
        var html =
            '<div class="card">' +
            '<div class="card-title">' +
            '<span>📊 ' + esc(vis.chart_title) + '</span>' +
            '<div style="font-size:0.85rem;font-weight:normal;color:var(--text-muted);">' +
            esc(vis.chart_subtitle) + '</div></div>' +
            '<div id="mainTelemetryChart" style="width:100%;height:420px;"></div></div>' +

            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">' +
            '<div class="card"><div class="card-title">📉 Soil Depth Gradient Attenuation</div>' +
            '<p class="card-subtitle">Vertical profile of microbial biomass across the archived soil depth horizons</p>' +
            '<div id="depthProfileChart" style="width:100%;height:350px;"></div></div>' +
            '<div class="card"><div class="card-title">🔬 ' + esc(vis.kin_title) + '</div>' +
            '<p class="card-subtitle">' + esc(vis.kin_subtitle) + '</p>' +
            '<div id="stoichiometryChart" style="width:100%;height:350px;"></div></div></div>';

        if (vis.records && vis.records.length) {
            var head = vis.columns.map(function (col) { return '<th>' + esc(col) + '</th>'; }).join('');
            var body = vis.records.map(function (row) {
                var cells = vis.columns.map(function (col) {
                    return '<td>' + safeCell(row[col]) + '</td>';
                }).join('');
                return '<tr>' + cells + '</tr>';
            }).join('');

            html += '<div class="card"><div class="card-title">' +
                '<span>📋 Raw Physical Data Table Snapshot (First ' + vis.records.length + ' Records)</span>' +
                '<span style="font-size:0.82rem;color:var(--text-muted);font-weight:normal;">' +
                esc(vis.total_count) + '</span></div>' +
                '<div style="overflow-x:auto;"><table class="data-table">' +
                '<thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div></div>';
        }

        return html;
    }

    function disposeCharts() {
        charts.forEach(function (chart) {
            try { chart.dispose(); } catch (err) { /* noop */ }
        });
        charts = [];
    }

    function initDetailCharts(vis) {
        if (typeof echarts === 'undefined') return;

        var mainDom = document.getElementById('mainTelemetryChart');
        if (mainDom) {
            var mainChart = echarts.init(mainDom);
            var isCsv = vis.data_type === 'csv';
            var legend = [vis.series1_name, vis.series2_name];
            if (vis.series3_name) legend.push(vis.series3_name);

            var series = [
                {
                    name: vis.series1_name,
                    type: isCsv ? 'bar' : 'line',
                    smooth: true,
                    data: vis.series1_data,
                    itemStyle: { color: '#2e7d32' },
                    lineStyle: { width: 2.5 }
                },
                {
                    name: vis.series2_name,
                    type: isCsv ? 'bar' : 'line',
                    smooth: true,
                    data: vis.series2_data,
                    itemStyle: { color: '#1565c0' },
                    lineStyle: { width: 2 }
                }
            ];

            if (vis.series3_name && vis.series3_data) {
                series.push({
                    name: vis.series3_name,
                    type: isCsv ? 'bar' : 'line',
                    smooth: true,
                    data: vis.series3_data,
                    itemStyle: { color: '#e65100' },
                    lineStyle: { type: 'dashed' }
                });
            }

            mainChart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
                legend: { data: legend, top: 0, type: 'scroll' },
                grid: { left: '10%', right: '4%', bottom: '18%', containLabel: true },
                dataZoom: [
                    { type: 'slider', show: true, xAxisIndex: [0], start: 0, end: 100, bottom: 5 },
                    { type: 'inside', xAxisIndex: [0] }
                ],
                xAxis: {
                    type: 'category',
                    boundaryGap: isCsv,
                    data: vis.x_labels,
                    name: vis.x_axis_name,
                    nameLocation: 'middle',
                    nameGap: 52,
                    axisLabel: {
                        interval: isCsv ? 0 : Math.ceil(vis.x_labels.length / 18),
                        rotate: isCsv ? 25 : 45,
                        hideOverlap: true
                    }
                },
                yAxis: {
                    type: 'value',
                    name: 'Biomass / Concentration (mmol/kg)',
                    nameLocation: 'middle',
                    nameRotate: 90,
                    nameGap: 62,
                    axisLine: { show: true, lineStyle: { color: '#245d3e' } }
                },
                series: series
            });
            charts.push(mainChart);
        }

        var depthDom = document.getElementById('depthProfileChart');
        if (depthDom) {
            var depthChart = echarts.init(depthDom);
            depthChart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
                legend: { data: ['Microbial C (mmol/kg)', 'Microbial N (mmol/kg)'], top: 0 },
                grid: { left: '4%', right: '5%', bottom: '14%', containLabel: true },
                xAxis: {
                    type: 'value',
                    name: 'Concentration (mmol/kg)',
                    nameLocation: 'middle',
                    nameGap: 30
                },
                yAxis: {
                    type: 'category',
                    inverse: true,
                    data: vis.depth_labels
                },
                series: [
                    {
                        name: 'Microbial C (mmol/kg)', type: 'line', smooth: true,
                        data: vis.depth_c, itemStyle: { color: '#2e7d32' },
                        areaStyle: { opacity: 0.15 }
                    },
                    {
                        name: 'Microbial N (mmol/kg)', type: 'line', smooth: true,
                        data: vis.depth_n, itemStyle: { color: '#1565c0' },
                        areaStyle: { opacity: 0.15 }
                    }
                ]
            });
            charts.push(depthChart);
        }

        var kinDom = document.getElementById('stoichiometryChart');
        if (kinDom) {
            var kinChart = echarts.init(kinDom);
            kinChart.setOption({
                tooltip: { trigger: 'axis' },
                grid: { left: '14%', right: '6%', bottom: '14%', containLabel: true },
                xAxis: {
                    type: 'value',
                    name: vis.kin_x_label,
                    nameLocation: 'middle',
                    nameGap: 30,
                    scale: true
                },
                yAxis: {
                    type: 'value',
                    name: vis.kin_y_label,
                    nameLocation: 'middle',
                    nameRotate: 90,
                    nameGap: 52,
                    scale: true
                },
                series: [{
                    name: 'Stoichiometric Scaling',
                    type: 'line',
                    smooth: true,
                    showSymbol: false,
                    data: vis.kin_x.map(function (x, index) {
                        return [x, vis.kin_y[index]];
                    }),
                    itemStyle: { color: '#245d3e' },
                    lineStyle: { width: 3 },
                    areaStyle: {
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            { offset: 0, color: 'rgba(36, 93, 62, 0.4)' },
                            { offset: 1, color: 'rgba(36, 93, 62, 0.02)' }
                        ])
                    }
                }]
            });
            charts.push(kinChart);
        }
    }

    /* --------------------------------------------------------------- exports */

    window.App = {
        applySlicerFilters: applySlicerFilters,
        resetFilters: resetFilters,
        toggleTags: function () {
            state.tagsExpanded = !state.tagsExpanded;
            renderKeyTags();
        },
        toggleBiome: function (box) {
            state.biomes[box.getAttribute('data-biome')] = box.checked;
            renderDatasetCards();
        },
        toggleVariable: function (box) {
            state.variables[box.getAttribute('data-code')] = box.checked;
            renderDatasetCards();
        },
        applyKeyword: function (tag) {
            state.query = tag;
            var qEl = document.getElementById('searchQuery');
            if (qEl) qEl.value = tag;
            if (window.location.hash !== '#/' && window.location.hash !== '') {
                window.location.hash = '#/';
            } else {
                renderDatasetCards();
            }
            showToast('Filtered by taxonomy tag: ' + tag);
        }
    };

    /* Backwards-compatible global handlers used by the static markup. */
    window.applySlicerFilters = applySlicerFilters;
    window.resetFilters = resetFilters;
    window.toggleMoreKeywords = window.App.toggleTags;

    /* ----------------------------------------------------------------- boot */

    function boot() {
        var datasetCount = document.getElementById('statBadgeDatasets');
        var keywordCount = document.getElementById('statBadgeKeywords');
        var variableCount = document.getElementById('statBadgeVariables');

        if (datasetCount) datasetCount.textContent = 'Managed Datasets: ' + DATA.datasets.length;
        if (keywordCount) keywordCount.textContent = 'Scientific Taxonomy Tags: ' + DATA.keywords.length;
        if (variableCount) variableCount.textContent = 'Variables: ' + DATA.variables.length;

        populateFilters();
        renderDatasetCards();

        window.addEventListener('hashchange', renderRoute);
        window.addEventListener('resize', function () {
            charts.forEach(function (chart) {
                try { chart.resize(); } catch (err) { /* noop */ }
            });
        });

        renderRoute();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();

/**
 * ClassPhoto Admin 热区可视化 v6
 * - 半透明大图浮层（pointer-events 穿透，不阻挡编辑）
 * - 悬停/点击热区行 → 红圈标注
 * - ↑↓ 键切换行
 */
(function () {
    'use strict';

    function showFatal(msg) {
        var d = document.createElement('div');
        d.style.cssText = 'position:fixed;top:0;left:0;right:0;background:red;color:white;padding:8px;z-index:99999;font-weight:bold;text-align:center;';
        d.textContent = '❌ 热区脚本错误: ' + msg;
        if (document.body) document.body.appendChild(d);
    }

    function init() {
        var dbg = document.createElement('div');
        dbg.id = 'hz-debug';
        dbg.style.cssText = 'background:#667eea;color:#fff;text-align:center;padding:6px;font-size:13px;position:fixed;top:0;left:0;right:0;z-index:99999;font-weight:bold;';
        dbg.textContent = '⏳ 热区脚本已加载...';
        document.body.appendChild(dbg);

        var inlineGroup = document.querySelector('.inline-group');
        if (!inlineGroup) { dbg.textContent = '❌ 未找到热区表格'; return; }

        // 找图片 URL
        var imageUrl = null;
        var allLinks = document.querySelectorAll('a');
        for (var i = 0; i < allLinks.length; i++) {
            var h = allLinks[i].href || '';
            if (h.indexOf('class_photos') >= 0 || (h.indexOf('/media/') >= 0 && h.match(/\.(jpg|jpeg|png|webp)/i))) {
                imageUrl = h; break;
            }
        }
        if (!imageUrl) {
            var imgs = document.querySelectorAll('img');
            for (var j = 0; j < imgs.length; j++) {
                if ((imgs[j].src || '').indexOf('class_photos') >= 0) { imageUrl = imgs[j].src; break; }
            }
        }

        if (imageUrl) {
            dbg.textContent = '✅ 热区预览已激活（半透明浮层，可透视编辑）';
            createPanel(imageUrl, inlineGroup);
        } else {
            dbg.textContent = '⚠️ 未找到合照图片，仅启用行高亮';
        }
        setTimeout(function () {
            dbg.style.opacity = '0'; dbg.style.transition = 'opacity 0.5s';
            setTimeout(function () { if (dbg.parentNode) dbg.remove(); }, 600);
        }, 2500);

        setupRowHighlight(inlineGroup);
    }

    function createPanel(imageUrl, inlineGroup) {
        var style = document.createElement('style');
        style.textContent = [
            '.hz-row-active{background:#fff3cd!important;outline:3px solid #ff6b00!important;outline-offset:-1px}',
            '.hz-row-hover{background:#e8f4fd!important}',
            '#hz-panel{position:fixed;right:12px;top:45px;z-index:9999;width:58vw;max-width:860px;max-height:calc(100vh - 60px);opacity:0.78;pointer-events:none;transition:opacity 0.3s}',
            '#hz-panel:hover{opacity:0.95}',
            '#hz-panel img{display:block;width:100%;height:auto;border-radius:6px;pointer-events:none}',
            '#hz-panel .tip{color:#fff;font-size:12px;margin:3px 0 0;text-align:center;background:rgba(0,0,0,0.55);padding:3px 8px;border-radius:6px;pointer-events:none}',
            '#hz-highlight{position:absolute;border:2px solid #ff1744;background:rgba(255,23,68,0.25);border-radius:50%;display:none;box-shadow:0 0 12px rgba(255,0,0,0.6),0 0 28px rgba(255,0,0,0.3);z-index:10;pointer-events:none;animation:hz-pulse 1s ease-in-out infinite}',
            '@keyframes hz-pulse{0%,100%{border-color:#ff1744;box-shadow:0 0 12px rgba(255,0,0,0.6),0 0 28px rgba(255,0,0,0.3)}50%{border-color:#ff5252;box-shadow:0 0 18px rgba(255,0,0,0.8),0 0 36px rgba(255,0,0,0.45)}}',
            '#hz-label{position:absolute;z-index:11;background:#ff1744;color:#fff;font-size:14px;font-weight:bold;padding:4px 12px;border-radius:12px;display:none;transform:translate(-50%,-140%);white-space:nowrap;pointer-events:none;box-shadow:0 2px 12px rgba(0,0,0,0.5)}',
            '@media(max-width:1000px){#hz-panel{width:70vw}}',
            '@media(max-width:700px){#hz-panel{display:none}}'
        ].join('\n');
        document.head.appendChild(style);

        var panel = document.createElement('div');
        panel.id = 'hz-panel';
        panel.innerHTML = '<div id="hz-preview" style="position:relative;line-height:0;pointer-events:none;"><img id="hz-photo" src="' + imageUrl + '" alt="" style="pointer-events:none;"><div style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;"><div id="hz-highlight"></div><div id="hz-label"></div></div></div><p class="tip">💡 <b>悬停</b>行看红圈 · <b>单击</b>锁定 · <b>↑↓</b>切换 · 浮层可透视</p>';
        document.body.appendChild(panel);

        // 不挤压编辑区
        var mc = document.getElementById('content') || document.querySelector('#content-main');
        if (mc) mc.style.marginRight = '';

        var img = document.getElementById('hz-photo');
        var highlight = document.getElementById('hz-highlight');
        var labelEl = document.getElementById('hz-label');

        window._hzShowHighlight = function (row) {
            var c = window._hzGetCoords(row);
            if (!c) { highlight.style.display = 'none'; labelEl.style.display = 'none'; return; }
            var iw = img.clientWidth, ih = img.clientHeight;
            if (!iw || !ih) { setTimeout(function () { window._hzShowHighlight(row); }, 150); return; }
            var left = c.x / 100 * iw, top = c.y / 100 * ih;
            var w = c.w / 100 * iw, h = c.h / 100 * ih;
            var MIN = 14;
            if (w < MIN || h < MIN) { var cx = left + w / 2, cy = top + h / 2; left = Math.max(0, cx - MIN / 2); top = Math.max(0, cy - MIN / 2); w = h = MIN; }
            left = Math.min(Math.max(left, 0), iw - w);
            top = Math.min(Math.max(top, 0), ih - h);
            highlight.style.cssText = 'display:block;left:' + left + 'px;top:' + top + 'px;width:' + w + 'px;height:' + h + 'px;position:absolute;border:2px solid #ff1744;background:rgba(255,23,68,0.25);border-radius:50%;box-shadow:0 0 12px rgba(255,0,0,0.6),0 0 28px rgba(255,0,0,0.3);z-index:10;pointer-events:none;animation:hz-pulse 1s ease-in-out infinite;';
            var txt = window._hzGetLabel(row);
            if (txt) { labelEl.style.cssText = 'display:block;position:absolute;z-index:11;background:#ff1744;color:#fff;font-size:14px;font-weight:bold;padding:4px 12px;border-radius:12px;transform:translate(-50%,-140%);white-space:nowrap;pointer-events:none;box-shadow:0 2px 12px rgba(0,0,0,0.5);left:' + (left + w / 2) + 'px;top:' + Math.max(24, top) + 'px;'; labelEl.textContent = txt; }
        };
        window._hzHideHighlight = function () { highlight.style.display = 'none'; labelEl.style.display = 'none'; };

        // ===== 显示全部已有热区（淡色底圈） =====
        var allCirclesLayer = document.createElement('div');
        allCirclesLayer.id = 'hz-all-circles';
        allCirclesLayer.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:5;';
        document.getElementById('hz-preview').appendChild(allCirclesLayer);

        window._hzRefreshAll = function () {
            var iw = img.clientWidth, ih = img.clientHeight;
            if (!iw || !ih) { setTimeout(window._hzRefreshAll, 300); return; }
            var html = '';
            var rows = [];
            var allTrs = inlineGroup.querySelectorAll('tr');
            for (var i = 0; i < allTrs.length; i++) {
                if (allTrs[i].className.indexOf('dynamic-') >= 0 && !allTrs[i].classList.contains('empty-form')) rows.push(allTrs[i]);
            }
            for (var r = 0; r < rows.length; r++) {
                var c = window._hzGetCoords(rows[r]);
                if (!c) continue;
                var left = c.x / 100 * iw, top = c.y / 100 * ih;
                var w = c.w / 100 * iw, h = c.h / 100 * ih;
                if (w < 3 || h < 3) { w = h = 8; left -= 2; top -= 2; }
                left = Math.max(0, left); top = Math.max(0, top);
                html += '<div style="position:absolute;left:' + left + 'px;top:' + top + 'px;width:' + w + 'px;height:' + h + 'px;border:1px solid rgba(78,203,113,0.6);background:rgba(78,203,113,0.12);border-radius:50%;"></div>';
            }
            allCirclesLayer.innerHTML = html;
        };
        img.addEventListener('load', function () { setTimeout(window._hzRefreshAll, 400); });
        setTimeout(window._hzRefreshAll, 600);
    }

    function setupRowHighlight(inlineGroup) {
        window._hzGetCoords = function (row) {
            var nums = row.querySelectorAll('input[type="number"]'), x = null, y = null, w = null, h = null;
            for (var i = 0; i < nums.length; i++) {
                var n = nums[i].name, p = n.split('-'), last = p[p.length - 1];
                if (last === 'x' && p.length >= 2 && p[p.length - 2] !== 'max' && p[p.length - 2] !== 'min') x = parseFloat(nums[i].value);
                if (last === 'y' && p.length >= 2 && p[p.length - 2] !== 'max' && p[p.length - 2] !== 'min') y = parseFloat(nums[i].value);
                if (last === 'width') w = parseFloat(nums[i].value);
                if (last === 'height') h = parseFloat(nums[i].value);
            }
            if (x == null || y == null || w == null || h == null) return null;
            if (isNaN(x) || isNaN(y) || isNaN(w) || isNaN(h)) return null;
            if (x === 0 && y === 0 && w === 0 && h === 0) return null;
            return { x: x, y: y, w: w, h: h };
        };
        window._hzGetLabel = function (row) {
            var sel = row.querySelector('select');
            if (sel && sel.selectedIndex > 0) {
                var txt = sel.options[sel.selectedIndex].text;
                // 去掉 已选/未选 后缀
                return txt.replace(/\s*[✅⬜].*$/, '');
            }
            var rows = [];
            var allTrs = inlineGroup.querySelectorAll('tr');
            for (var i = 0; i < allTrs.length; i++) {
                if (allTrs[i].className.indexOf('dynamic-') >= 0 && !allTrs[i].classList.contains('empty-form')) rows.push(allTrs[i]);
            }
            var idx = rows.indexOf(row);
            return idx >= 0 ? 'No.' + (idx + 1) : '';
        };

        var lockedRow = null, hoverTimer = null;

        inlineGroup.addEventListener('mouseover', function (e) {
            var row = e.target.closest('tr');
            if (!row || row.className.indexOf('dynamic-') < 0 || row.classList.contains('empty-form')) return;
            if (lockedRow) return;
            clearTimeout(hoverTimer);
            row.classList.add('hz-row-hover');
            if (window._hzShowHighlight) window._hzShowHighlight(row);
        });

        inlineGroup.addEventListener('mouseout', function (e) {
            var row = e.target.closest('tr');
            if (!row) return;
            row.classList.remove('hz-row-hover');
            if (lockedRow) return;
            hoverTimer = setTimeout(function () { if (window._hzHideHighlight) window._hzHideHighlight(); }, 80);
        });

        inlineGroup.addEventListener('click', function (e) {
            var row = e.target.closest('tr');
            if (!row || row.className.indexOf('dynamic-') < 0 || row.classList.contains('empty-form')) return;
            if (lockedRow === row) {
                lockedRow = null; row.classList.remove('hz-row-active');
                if (window._hzHideHighlight) window._hzHideHighlight();
                if (window._hzRefreshAll) setTimeout(window._hzRefreshAll, 100);
            } else {
                if (lockedRow) lockedRow.classList.remove('hz-row-active');
                lockedRow = row; row.classList.add('hz-row-active');
                if (window._hzShowHighlight) { window._hzShowHighlight(row); setTimeout(function () { window._hzShowHighlight(row); }, 200); }
                if (window._hzRefreshAll) setTimeout(window._hzRefreshAll, 100);
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
            if (!inlineGroup.contains(document.activeElement) && document.activeElement.tagName !== 'BODY') return;
            var rows = [];
            var allTrs = inlineGroup.querySelectorAll('tr');
            for (var i = 0; i < allTrs.length; i++) {
                if (allTrs[i].className.indexOf('dynamic-') >= 0 && !allTrs[i].classList.contains('empty-form')) rows.push(allTrs[i]);
            }
            if (rows.length === 0) return;
            var idx = lockedRow ? rows.indexOf(lockedRow) : -1;
            if (e.key === 'ArrowDown') { e.preventDefault(); idx = Math.min(idx + 1, rows.length - 1); }
            else { e.preventDefault(); idx = Math.max(idx - 1, 0); }
            if (lockedRow) lockedRow.classList.remove('hz-row-active');
            lockedRow = rows[idx]; lockedRow.classList.add('hz-row-active');
            if (window._hzShowHighlight) window._hzShowHighlight(lockedRow);
            lockedRow.scrollIntoView({ block: 'center', behavior: 'smooth' });
        });

        // ===== 实时坐标编辑：修改 x/y/w/h 时红圈跟随移动 =====
        inlineGroup.addEventListener('input', function (e) {
            var inp = e.target;
            if (inp.tagName !== 'INPUT' || inp.type !== 'number') return;
            var row = inp.closest('tr');
            if (!row || row.className.indexOf('dynamic-') < 0) return;
            if (lockedRow === row) {
                if (window._hzShowHighlight) window._hzShowHighlight(row);
            } else {
                // 编辑任意行时临时显示红圈
                row.classList.add('hz-row-hover');
                if (window._hzShowHighlight) window._hzShowHighlight(row);
                clearTimeout(hoverTimer);
                hoverTimer = setTimeout(function () {
                    row.classList.remove('hz-row-hover');
                    if (!lockedRow && window._hzHideHighlight) window._hzHideHighlight();
                    if (window._hzRefreshAll) window._hzRefreshAll();
                }, 1500);
            }
        });

        // ===== 新空白行：自动填入同行平均宽高 =====
        function setDefaultSize(row) {
            var existing = window._hzGetCoords(row);
            if (existing && (existing.w > 0 || existing.h > 0)) return; // 已有值，跳过
            var yVal = parseFloat((row.querySelector('input[name$="-y"]') || {}).value);
            if (isNaN(yVal)) return;
            // 收集同行（Y接近）的热区宽高
            var ws = [], hs = [];
            var allTrs = inlineGroup.querySelectorAll('tr');
            for (var i = 0; i < allTrs.length; i++) {
                if (allTrs[i] === row || allTrs[i].classList.contains('empty-form')) continue;
                if (allTrs[i].className.indexOf('dynamic-') < 0) continue;
                var c = window._hzGetCoords(allTrs[i]);
                if (c && Math.abs(c.y - yVal) < 3) { ws.push(c.w); hs.push(c.h); }
            }
            if (ws.length > 0) {
                var avgW = ws.reduce(function (a, b) { return a + b; }, 0) / ws.length;
                var avgH = hs.reduce(function (a, b) { return a + b; }, 0) / hs.length;
                var wInp = row.querySelector('input[name$="-width"]');
                var hInp = row.querySelector('input[name$="-height"]');
                if (wInp && !wInp.value) wInp.value = avgW.toFixed(1);
                if (hInp && !hInp.value) hInp.value = avgH.toFixed(1);
            }
        }
        // 监听新行的 Y 坐标输入，自动填入宽高
        inlineGroup.addEventListener('change', function (e) {
            var inp = e.target;
            if (inp.tagName !== 'INPUT' || inp.type !== 'number') return;
            if (inp.name && inp.name.indexOf('-y') < 0) return;
            var row = inp.closest('tr');
            if (!row || row.className.indexOf('dynamic-') < 0) return;
            setDefaultSize(row);
        });

        var rt;
        window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (lockedRow && window._hzShowHighlight) window._hzShowHighlight(lockedRow); if (window._hzRefreshAll) window._hzRefreshAll(); }, 200); });
        var img = document.getElementById('hz-photo');
        if (img) img.addEventListener('load', function () { if (lockedRow && window._hzShowHighlight) window._hzShowHighlight(lockedRow); });
    }

    function startWhenReady() {
        if (!document.body) { setTimeout(startWhenReady, 50); return; }
        try { init(); } catch (e) { showFatal(e.message); }
    }
    if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', startWhenReady); }
    else { startWhenReady(); }
})();

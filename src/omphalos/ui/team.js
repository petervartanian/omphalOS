/* Optional, same-origin team transport. Never loaded by the public browser edition. */
'use strict';

(() => {
  const escape = (value) =>
    String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  const state = { user: null, csrf: '', matter: null, revision: null, stale: false, generation: 0 };
  let readyResolve;
  const ready = new Promise((resolve) => {
    readyResolve = resolve;
  });
  let dialog;
  let viewEpoch = 0;
  let approvalContext = null;
  const reviewDrafts = new Map();
  const adminRevisions = new Map();
  const draftKey = (context) => `${context.matter_id}/${context.run_id}/${context.package_sha256}`;
  function captureReviewDraft() {
    const form = document.querySelector('#team-decision');
    if (!approvalContext || !form) return;
    const note = form.querySelector('[name="note"]')?.value || '';
    if (note.trim())
      reviewDrafts.set(draftKey(approvalContext), {
        ...approvalContext,
        note,
        decision: form.querySelector('[name="decision"]')?.value || 'request_changes',
      });
    else reviewDrafts.delete(draftKey(approvalContext));
  }
  const drafts = () => {
    captureReviewDraft();
    return [...reviewDrafts.values()];
  };
  let requestCount = 0;
  const message = (text) => {
    const status = document.querySelector('#team-status');
    if (status) {
      status.textContent = text;
      status.hidden = !text;
    }
  };
  const fail = (text, status) => Object.assign(new Error(text), { status });

  async function send(path, body, expected) {
    const headers = {};
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      headers['X-Omphalos-CSRF'] = state.csrf;
      if (expected !== undefined) headers['If-Match'] = `"${expected}"`;
    }
    let response;
    try {
      response = await fetch(`/team/api/${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: 'same-origin',
        cache: 'no-store',
      });
    } catch {
      throw fail('The team server is unavailable. Your unsaved edits remain in this tab.', 0);
    }
    let result;
    try {
      result = await response.json();
    } catch {
      throw fail(
        'The server returned an unreadable response. Your unsaved edits remain in this tab.',
        response.status,
      );
    }
    if (!response.ok) {
      if (
        (response.status === 401 || (response.status === 403 && body === undefined)) &&
        state.matter
      )
        markStale(
          response.status === 401
            ? 'Your session has ended. Save any draft before signing in again.'
            : 'Your access may have changed. Save any draft before reopening the workspace.',
        );
      throw fail(result.error || `The request failed (${response.status}).`, response.status);
    }
    const raw = response.headers.get('X-Omphalos-Revision');
    const revision = raw === null ? null : Number(raw.replaceAll('"', ''));
    return { result, revision: Number.isSafeInteger(revision) && revision >= 0 ? revision : null };
  }

  function markStale(text = 'The shared workspace changed. Your unsaved edits are still here.') {
    state.stale = true;
    let banner = document.querySelector('#team-update');
    if (!banner) {
      banner = document.createElement('section');
      banner.id = 'team-update';
      banner.className = 'team-update';
      banner.setAttribute('role', 'status');
      banner.innerHTML =
        '<p></p><div class="actions"><button type="button" class="secondary" data-team="save-draft">Save draft copy</button><button type="button" data-team="reload">Reload shared version</button></div><small>Reloading discards unsaved edits. Save a draft copy first if needed.</small>';
      document.querySelector('#main').before(banner);
    }
    banner.querySelector('p').textContent = text;
  }

  function acceptRevision(revision, mutation = false) {
    if (revision === null) {
      markStale('The server did not return a workspace revision. Save any draft before reloading.');
      throw fail('The team server omitted the workspace revision. Reload before editing.', 0);
    }
    if (state.revision === null || mutation) state.revision = revision;
    else if (revision !== state.revision) markStale();
  }

  async function scoped(path, body) {
    if (!state.matter) throw fail('Choose a shared workspace first.', 400);
    if (body !== undefined && state.stale)
      throw fail(
        'Reload the shared version before saving. Save a draft copy first if needed.',
        409,
      );
    const matterId = state.matter.id;
    const generation = state.generation;
    const expected = state.revision;
    requestCount += 1;
    try {
      const reply = await send(
        `matters/${encodeURIComponent(matterId)}/${path}`,
        body,
        body === undefined ? undefined : expected,
      );
      if (generation !== state.generation)
        throw fail('The selected workspace changed. Reopen the current workspace.', 409);
      acceptRevision(reply.revision, body !== undefined);
      return reply.result;
    } catch (error) {
      if (error.status === 409) markStale();
      throw error;
    } finally {
      requestCount -= 1;
    }
  }

  async function request(path, body) {
    await ready;
    return scoped(`engine/${path}`, body);
  }

  function panel(title, content, close = true) {
    captureReviewDraft();
    viewEpoch += 1;
    approvalContext = null;
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.id = 'team-dialog';
      dialog.setAttribute('aria-labelledby', 'team-title');
      dialog.addEventListener('close', () => {
        captureReviewDraft();
        viewEpoch += 1;
        approvalContext = null;
      });
      document.body.append(dialog);
    }
    dialog.innerHTML = `<div class="dialog-heading"><h2 id="team-title">${escape(title)}</h2>${close ? '<button type="button" class="secondary" data-team="close">Close</button>' : ''}</div><div id="team-content">${content}</div><p id="team-status" role="alert" hidden></p>`;
    if (!dialog.open) dialog.showModal();
  }

  function header() {
    let control = document.querySelector('#team-account');
    if (!control) {
      control = document.createElement('button');
      control.id = 'team-account';
      control.type = 'button';
      control.className = 'text-button';
      control.dataset.team = 'workspaces';
      document.querySelector('.topbar-actions').prepend(control);
    }
    control.textContent = state.matter ? state.matter.title : 'Shared workspaces';
    control.title = `${state.user.display_name}${state.matter ? ` · ${state.matter.role}` : ''}`;
  }

  function login() {
    document.querySelector('#main').innerHTML =
      '<section class="team-welcome"><h1>Sign in to your team</h1><form id="team-login"><div class="field"><label for="team-username">Username</label><input id="team-username" name="username" autocomplete="username" required maxlength="64"></div><div class="field"><label for="team-password">Password</label><input id="team-password" name="password" type="password" autocomplete="current-password" required maxlength="256"></div><button type="submit">Sign in</button><p id="team-status" role="alert" hidden></p></form></section>';
  }

  async function workspaces() {
    captureReviewDraft();
    const epoch = ++viewEpoch;
    approvalContext = null;
    const { result } = await send('matters');
    if (epoch !== viewEpoch) return;
    const items = result.matters
      .map(
        (matter) =>
          `<button type="button" class="team-matter" data-team="select" data-id="${escape(matter.id)}"><strong>${escape(matter.title)}</strong><span>${escape(matter.role)}</span><span aria-hidden="true">→</span></button>`,
      )
      .join('');
    panel(
      'Shared workspaces',
      `<p class="small muted">${escape(state.user.display_name)}</p><div class="team-matters">${items || '<p>You have no assigned workspaces. Your administrator can grant access.</p>'}</div><div class="actions">${state.user.is_admin ? '<button type="button" class="secondary" data-team="admin">Manage team</button>' : ''}<button type="button" class="text-button" data-team="password">Change password</button><button type="button" class="text-button" data-team="logout">Sign out</button></div>`,
      Boolean(state.matter),
    );
  }

  async function select(id) {
    const { result } = await send('matters');
    const matter = result.matters.find((item) => item.id === id);
    if (!matter) throw fail('This workspace is no longer available to your account.', 403);
    if (state.matter?.id === id) {
      dialog?.close();
      return;
    }
    if (state.matter && state.matter.id !== id) {
      if (window.omphalosTeam.canLeave && !window.omphalosTeam.canLeave()) return;
      window.sessionStorage.setItem('omphalos-team-matter', id);
      location.reload();
      return;
    }
    state.matter = matter;
    document.body.dataset.teamRole = matter.role;
    state.revision = null;
    state.generation += 1;
    window.sessionStorage.setItem('omphalos-team-matter', id);
    dialog?.close();
    header();
    readyResolve();
    poll(state.generation);
  }

  async function poll(generation) {
    while (generation === state.generation && state.matter && !state.stale) {
      try {
        const after = state.revision ?? state.matter.revision;
        const { result } = await send(
          `matters/${encodeURIComponent(state.matter.id)}/events?after=${after}&wait=20`,
        );
        if (generation !== state.generation) return;
        // A response racing our own save is checked on the next request, never rebased here.
        if (!requestCount && state.revision !== null && result.revision > state.revision)
          markStale();
      } catch (error) {
        if ([401, 403].includes(error.status)) return;
        await new Promise((resolve) => setTimeout(resolve, 5000));
      }
      // Avoid a tight loop if a proxy returns a long poll early.
      await new Promise((resolve) => setTimeout(resolve, 750));
    }
  }

  async function admin() {
    captureReviewDraft();
    const epoch = ++viewEpoch;
    approvalContext = null;
    const [users, matters] = await Promise.all([send('admin/users'), send('admin/matters')]);
    if (epoch !== viewEpoch) return;
    const userOptions = users.result.users
      .filter((u) => u.active)
      .map(
        (u) =>
          `<option value="${escape(u.id)}">${escape(u.display_name)} (${escape(u.username)})</option>`,
      )
      .join('');
    adminRevisions.clear();
    matters.result.matters.forEach((matter) => adminRevisions.set(matter.id, matter.revision));
    const matterOptions = matters.result.matters
      .map((m) => `<option value="${escape(m.id)}">${escape(m.title)}</option>`)
      .join('');
    panel(
      'Manage team',
      `<nav class="actions"><button type="button" class="text-button" data-team="workspaces">← Workspaces</button></nav><section class="flow-section"><h3>Workspace access</h3>${matterOptions && userOptions ? `<form id="team-membership"><div class="field"><label for="team-member-matter">Workspace</label><select id="team-member-matter" name="matter_id">${matterOptions}</select></div><div class="field"><label for="team-member-user">Person</label><select id="team-member-user" name="user_id">${userOptions}</select></div><div class="field"><label for="team-member-role">Role</label><select id="team-member-role" name="role" required><option value="" disabled selected>Choose access</option><option value="analyst">Analyst — work on records and assessments</option><option value="reviewer">Reviewer — review submitted packages</option><option value="viewer">Viewer — read and download</option><option value="remove">Remove access</option></select></div><button type="submit">Update access</button><button type="button" class="text-button" data-team="members">View current access</button></form>` : '<p>Create a workspace and an account to assign access.</p>'}<div id="team-members"></div></section><section class="flow-section"><h3>New workspace</h3><form id="team-new-matter"><div class="field"><label for="team-matter-title">Title</label><input id="team-matter-title" name="title" required maxlength="120"></div><button type="submit" class="secondary">Create workspace</button></form></section><section class="flow-section"><h3>New account</h3><form id="team-new-user"><div class="field"><label for="team-user-name">Username</label><input id="team-user-name" name="username" autocomplete="off" required maxlength="64"></div><div class="field"><label for="team-user-display">Name</label><input id="team-user-display" name="display_name" required maxlength="120"></div><div class="field"><label for="team-user-password">Initial password</label><input id="team-user-password" name="password" type="password" autocomplete="new-password" required minlength="14" maxlength="256"></div><p class="small muted">Share the initial password through your existing secure channel. The account holder can change it after signing in.</p><label class="inline-check"><input type="checkbox" name="is_admin" value="true"><span>Administrator: manage accounts and workspace access</span></label><button type="submit" class="secondary">Create account</button></form></section><section class="flow-section"><h3>Accounts</h3>${users.result.users.map((u) => `<div class="team-user-row"><span>${escape(u.display_name)} <small>${escape(u.username)} · ${u.active ? 'Active' : 'Disabled'}</small></span>${u.id !== state.user.id ? `<div class="actions"><button type="button" class="text-button" data-team="reset-password" data-id="${escape(u.id)}" data-name="${escape(u.display_name)}">Reset password</button><button type="button" class="text-button" data-team="user-active" data-id="${escape(u.id)}" data-active="${!u.active}">${u.active ? 'Disable' : 'Enable'}</button></div>` : ''}</div>`).join('')}</section>`,
    );
  }

  async function members() {
    const id = document.querySelector('#team-member-matter')?.value;
    const epoch = viewEpoch;
    const { result, revision } = await send(`admin/matters/${encodeURIComponent(id)}/members`);
    if (epoch !== viewEpoch || document.querySelector('#team-member-matter')?.value !== id) return;
    if (revision !== null) adminRevisions.set(id, revision);
    document.querySelector('#team-members').innerHTML =
      `<ul class="compact-list">${result.members.map((m) => `<li>${escape(m.display_name || m.user?.display_name || m.user_id)} · ${escape(m.role)}</li>`).join('') || '<li>No assigned members.</li>'}</ul>`;
  }

  async function review(context) {
    if (!context) throw fail('Create the current evidence package before requesting review.', 400);
    captureReviewDraft();
    const epoch = ++viewEpoch;
    approvalContext = null;
    const captured = Object.freeze({
      ...context,
      matter_id: state.matter.id,
      base_revision: context.base_revision ?? state.revision,
    });
    const result = await scoped(`approval?run_id=${encodeURIComponent(captured.run_id)}`);
    if (epoch !== viewEpoch) return;
    if (
      result.package?.package_sha256 !== captured.package_sha256 ||
      result.package?.run_id !== captured.run_id
    ) {
      markStale('The package changed. Reload it before requesting or recording a review.');
      throw fail('The package changed. Reload it before review.', 409);
    }
    const draft = reviewDrafts.get(draftKey(captured));
    const current = result.decisions.filter((item) => item.current);
    const distinct = new Set(current.map((item) => item.decision));
    const summary =
      distinct.size > 1
        ? '<p class="callout error">Reviewers disagree. Resolve the conflicting decisions before relying on approval.</p>'
        : '';
    const history = result.decisions
      .map(
        (item) =>
          `<section class="flow-section"><h3>${item.decision === 'approve' ? 'Approved' : 'Changes requested'} · ${escape(item.reviewer.display_name)}</h3><p>${escape(item.note)}</p><p class="small muted">${escape(item.at)}${item.current ? '' : ' · Earlier package'}</p></section>`,
      )
      .join('');
    panel(
      'Team review',
      `${summary}<p>${result.submission ? `Submitted by ${escape(result.submission.submitted_by.display_name)}.` : 'This package has not been submitted for review.'}</p>${result.submission_blocker ? `<p>${escape(result.submission_blocker)}</p>` : ''}<p class="small mono word-break">Package ${escape(result.package?.package_sha256 || 'unavailable')}</p>${result.can_submit ? '<button type="button" data-team="submit-package">Submit this package for review</button>' : ''}${result.can_review ? `<form id="team-decision"><div class="field"><label for="team-decision-value">Decision</label><select id="team-decision-value" name="decision"><option value="request_changes">Request changes</option><option value="approve" ${draft?.decision === 'approve' ? 'selected' : ''}>Approve this package</option></select></div><div class="field"><label for="team-decision-note">Review note</label><textarea id="team-decision-note" name="note" rows="4" required maxlength="4000">${escape(draft?.note || '')}</textarea></div><button type="submit">Record review</button></form>` : ''}${history || '<p class="small muted">No team review recorded.</p>'}`,
    );
    approvalContext = captured;
  }

  function passwordForm() {
    panel(
      'Change password',
      '<form id="team-password-change"><div class="field"><label for="team-old-password">Current password</label><input id="team-old-password" name="current_password" type="password" autocomplete="current-password" required></div><div class="field"><label for="team-new-password">New password</label><input id="team-new-password" name="new_password" type="password" autocomplete="new-password" required minlength="14" maxlength="256"></div><button type="submit">Change password</button></form>',
    );
  }

  async function click(button) {
    const action = button.dataset.team;
    if (action === 'close') {
      captureReviewDraft();
      viewEpoch += 1;
      approvalContext = null;
      dialog.close();
    }
    if (action === 'workspaces') await workspaces();
    if (action === 'select') await select(button.dataset.id);
    if (action === 'admin') await admin();
    if (action === 'members') await members();
    if (action === 'password') passwordForm();
    if (action === 'reset-password')
      panel(
        `Reset password · ${button.dataset.name}`,
        `<p>Changing this password ends the account's active sessions.</p><form id="team-admin-password" data-user-id="${escape(button.dataset.id)}"><div class="field"><label for="team-reset-password">New temporary password</label><input id="team-reset-password" name="password" type="password" autocomplete="new-password" required minlength="14" maxlength="256"></div><button type="submit">Reset this account's password</button></form>`,
      );
    if (action === 'reload') location.reload();
    if (action === 'save-draft') window.dispatchEvent(new window.Event('omphalos-team-save-draft'));
    if (action === 'logout') {
      if (window.omphalosTeam.canLeave && !window.omphalosTeam.canLeave()) return;
      if (state.matter) window.dispatchEvent(new window.Event('omphalos-team-before-logout'));
      await send('logout', {});
      state.generation += 1;
      location.reload();
    }
    if (action === 'user-active') {
      await send(`admin/users/${encodeURIComponent(button.dataset.id)}`, {
        active: button.dataset.active === 'true',
      });
      await admin();
    }
    if (action === 'submit-package') {
      const captured = approvalContext;
      if (!captured) throw fail('Reopen the current package before submitting it.', 409);
      await scoped('submission', {
        run_id: captured.run_id,
        package_sha256: captured.package_sha256,
      });
      if (approvalContext === captured) await review(captured);
    }
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-team]');
    if (!button || button.disabled) return;
    event.preventDefault();
    button.disabled = true;
    Promise.resolve(click(button))
      .catch((error) => message(error.message))
      .finally(() => {
        button.disabled = false;
      });
  });
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.id.startsWith('team-')) return;
    event.preventDefault();
    if (form.dataset.busy) return;
    form.dataset.busy = 'true';
    const values = Object.fromEntries(new FormData(form));
    const capturedReview = form.id === 'team-decision' ? approvalContext : null;
    captureReviewDraft();
    const controls = [...form.querySelectorAll('input, select, textarea, button')];
    const disabled = controls.map((control) => control.disabled);
    controls.forEach((control) => {
      control.disabled = true;
    });
    const button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    Promise.resolve()
      .then(async () => {
        if (form.id === 'team-login') {
          const { result } = await send('login', values);
          form.reset();
          Object.assign(state, { user: result.user, csrf: result.csrf });
          header();
          await chooseInitial();
        } else if (form.id === 'team-new-matter') {
          await send('matters', values);
          await admin();
        } else if (form.id === 'team-new-user') {
          await send('admin/users', { ...values, is_admin: values.is_admin === 'true' });
          form.reset();
          await admin();
        } else if (form.id === 'team-membership') {
          await send(
            `admin/matters/${encodeURIComponent(values.matter_id)}/members`,
            {
              user_id: values.user_id,
              role: values.role === 'remove' ? null : values.role,
            },
            adminRevisions.get(values.matter_id),
          );
          await members();
          message('Access updated.');
        } else if (form.id === 'team-decision') {
          if (!capturedReview)
            throw fail('Reopen the current package before recording its review.', 409);
          await scoped('approval', {
            ...values,
            run_id: capturedReview.run_id,
            package_sha256: capturedReview.package_sha256,
          });
          reviewDrafts.delete(draftKey(capturedReview));
          if (approvalContext === capturedReview) {
            approvalContext = null;
            await review(capturedReview);
          }
        } else if (form.id === 'team-admin-password') {
          await send(`admin/users/${encodeURIComponent(form.dataset.userId)}`, values);
          form.reset();
          await admin();
          message('Password reset. Share it through your existing secure channel.');
        } else if (form.id === 'team-password-change') {
          await send('password', values);
          form.reset();
          message('Password changed. Sign in again.');
          state.generation += 1;
          location.reload();
        }
      })
      .catch((error) => message(error.message))
      .finally(() => {
        delete form.dataset.busy;
        controls.forEach((control, index) => {
          control.disabled = disabled[index];
        });
        if (button) button.disabled = false;
      });
  });

  async function chooseInitial() {
    const saved = window.sessionStorage.getItem('omphalos-team-matter');
    if (saved) {
      const { result } = await send('matters');
      if (result.matters.some((item) => item.id === saved)) return select(saved);
      window.sessionStorage.removeItem('omphalos-team-matter');
    }
    await workspaces();
  }

  async function init() {
    const { result } = await send('session');
    if (!result.authenticated) login();
    else {
      Object.assign(state, { user: result.user, csrf: result.csrf });
      header();
      await chooseInitial();
    }
    return ready;
  }
  document.addEventListener('input', (event) => {
    if (event.target.closest('#team-decision')) captureReviewDraft();
  });
  document.addEventListener('change', (event) => {
    if (event.target.closest('#team-decision')) captureReviewDraft();
  });
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      document.querySelector('#main').textContent = 'Checking your session…';
      location.reload();
    }
  });
  window.addEventListener('beforeunload', (event) => {
    if (drafts().length) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  window.omphalosTeam = {
    drafts,
    init,
    request,
    review,
    get state() {
      return state;
    },
  };
})();

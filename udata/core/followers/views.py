# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from flask import url_for, redirect

from udata.auth import current_user

from udata.i18n import I18nBlueprint
from udata.frontend.views import DetailView

from udata.core.organization.views import OrgView
from udata.core.dataset.views import DatasetView
from udata.core.user.views import UserView

from .models import Follow, FollowOrg, FollowDataset

blueprint = I18nBlueprint('followers', __name__)


@blueprint.app_template_global()
@blueprint.app_template_filter()
def is_following(obj):
    return current_user.is_authenticated() and Follow.objects.is_following(current_user._get_current_object(), obj)


class UserFollowersView(UserView, DetailView):
    template_name = 'user/followers.html'

    def get_context(self):
        context = super(UserFollowersView, self).get_context()
        context['followers'] = Follow.objects.followers(self.user).order_by('follower.fullname')
        return context


class UserFollowingView(UserView, DetailView):
    template_name = 'user/following.html'

    def get_context(self):
        context = super(UserFollowingView, self).get_context()
        datasets, organizations, users = [], [], []
        for follow in Follow.objects.following(self.user):
            if isinstance(follow, FollowOrg):
                organizations.append(follow)
            elif isinstance(follow, FollowDataset):
                datasets.append(follow)
            else:
                users.append(follow)

        context.update({
            'followed_datasets': sorted(datasets, key=lambda f: f.following.title),
            'followed_organizations': sorted(organizations, key=lambda f: f.following.name),
            'followed_users': sorted(users, key=lambda f: f.following.fullname),
        })
        return context


class OrganizationFollowersView(OrgView, DetailView):
    template_name = 'organization/followers.html'

    def get_context(self):
        context = super(OrganizationFollowersView, self).get_context()
        context['followers'] = Follow.objects.followers(self.organization).order_by('follower.fullname')
        return context


class DatasetFollowersView(DatasetView, DetailView):
    template_name = 'dataset/followers.html'

    def get_context(self):
        context = super(DatasetFollowersView, self).get_context()
        context['followers'] = Follow.objects.followers(self.dataset).order_by('follower.fullname')
        return context


blueprint.add_url_rule(
    '/organizations/<org:org>/followers/',
    view_func=OrganizationFollowersView.as_view(str('organization'))
)

blueprint.add_url_rule(
    '/datasets/<dataset:dataset>/followers/',
    view_func=DatasetFollowersView.as_view(str('dataset'))
)

blueprint.add_url_rule(
    '/u/<user:user>/followers/',
    view_func=UserFollowersView.as_view(str('user'))
)

blueprint.add_url_rule(
    '/u/<user:user>/following/',
    view_func=UserFollowingView.as_view(str('user_following'))
)
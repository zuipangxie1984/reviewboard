import os
import shutil
import tempfile

from django.conf import settings
from django.forms import ValidationError
from django.test import TestCase
from django.test import Client
from djblets.siteconfig.models import SiteConfiguration

from reviewboard.admin import checks
from reviewboard.ssh.client import SSHClient
from reviewboard.admin.validation import validate_bug_tracker
from reviewboard.site.urlresolvers import local_site_reverse


class UpdateTests(TestCase):
    """Tests for update required pages"""

    def tearDown(self):
        # Make sure we don't break further tests by resetting this fully.
        checks.reset_check_cache()

    def testManualUpdatesRequired(self):
        """Testing check_updates_required with valid configuration"""
        # NOTE: This is assuming the install is fine. It should be given
        #       that we set things like the uploaded path correctly to
        #       a known good directory before starting unit tests.
        updates_required = checks.check_updates_required()

        self.assertEqual(len(updates_required), 0)

    def testManualUpdatesRequiredBadUpload(self):
        """Testing check_updates_required with a bad upload directory"""
        siteconfig = SiteConfiguration.objects.get_current()

        old_media_root = settings.MEDIA_ROOT
        siteconfig.set('site_media_root', '/')
        siteconfig.save()
        settings.MEDIA_ROOT = "/"
        checks.reset_check_cache()

        updates_required = checks.check_updates_required()
        self.assertEqual(len(updates_required), 1)

        url, data = updates_required[0]
        self.assertEqual(url, "admin/manual-updates/media-upload-dir.html")

        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/manual_updates_required.html")

        settings.MEDIA_ROOT = old_media_root
        siteconfig.set('site_media_root', old_media_root)
        siteconfig.save()

        # Make sure that the site works again once the media root is fixed.
        response = self.client.get("/dashboard/")
        self.assertTemplateNotUsed(response,
                                   "admin/manual_updates_required.html")


class ValidatorTests(TestCase):
    def test_validate_bug_tracker(self):
        """Testing bug tracker url form field validation"""
        # Invalid - invalid format specification types
        self.assertRaises(ValidationError, validate_bug_tracker, "%20")
        self.assertRaises(ValidationError, validate_bug_tracker, "%d")

        # Invalid - too many format specification types
        self.assertRaises(ValidationError, validate_bug_tracker, "%s %s")

        # Invalid - no format specification types
        self.assertRaises(ValidationError, validate_bug_tracker, "www.a.com")

        # Valid - Escaped %'s, with a valid format specification type
        try:
            validate_bug_tracker("%%20%s")
        except ValidationError:
            self.assertFalse(True, "validate_bug_tracker() raised a "
                                   "ValidationError when no error was "
                                   "expected.")


class SSHSettingsFormTestCase(TestCase):
    """Unit tests for SSHSettingsForm in /admin/forms.py"""
    fixtures = ['test_users']

    def setUp(self):
        # Setup temp directory to prevent the original ssh related
        # configurations been overwritten.
        self.old_home = os.getenv('HOME')
        self.tempdir = tempfile.mkdtemp(prefix='rb-tests-home-')
        os.environ['RBSSH_ALLOW_AGENT'] = '0'
        self._set_home(self.tempdir)

        # Init client for http request, ssh_client for ssh config manipulation.
        self.client = Client()
        self.ssh_client = SSHClient()

    def tearDown(self):
        self._set_home(self.old_home)

        if self.tempdir:
            shutil.rmtree(self.tempdir)

    def _set_home(self, homedir):
        os.environ['HOME'] = homedir

    def test_generate_key(self):
        """Testing SSHSettingsForm POST with generate_key=1"""

        # Should have no ssh key at this point.
        self.assertEqual(self.ssh_client.get_user_key(), None)

        # Send post request with 'generate_key' = 1.
        self.client.login(username='admin', password='admin')
        response = self.client.post(local_site_reverse('settings-ssh'), {
            'generate_key': 1,
        })

        # Check the response's status_code,
        # 302 means the request has been proceeded as POST.
        self.assertEqual(response.status_code, 302)

        # Check whether the key has been created.
        self.assertNotEqual(self.ssh_client.get_user_key(), None)

    def test_delete_key(self):
        """Testing SSHSettingsForm POST with delete_key=1"""

        # Should have no ssh key at this point, generate one.
        self.assertEqual(self.ssh_client.get_user_key(), None)
        self.ssh_client.generate_user_key()
        self.assertNotEqual(self.ssh_client.get_user_key(), None)

        # Send post request with 'delete_key' = 1.
        self.client.login(username='admin', password='admin')
        response = self.client.post(local_site_reverse('settings-ssh'), {
            'delete_key': 1,
        })

        # Check the response's status_code,
        # 302 means the request has been proceeded as POST.
        self.assertEqual(response.status_code, 302)

        # Check whether the key has been deleted.
        self.assertEqual(self.ssh_client.get_user_key(), None)

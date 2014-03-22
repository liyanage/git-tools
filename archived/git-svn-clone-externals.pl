#!/usr/bin/perl
#
# Recursively clone svn:externals in a git-svn sandbox.
#
# Written by Marc Liyanage <http://www.entropy.ch>
#
# See http://github.com/liyanage/git-tools
#
# Note: This Perl version has less features than the Ruby version, you should use that one instead.
#

use strict;
use warnings;

use Cwd;
use IO::Dir;
use File::Path;
use File::Basename;

$ENV{PATH} = "/opt/local/bin:$ENV{PATH}";

my $processor = ExternalsProcessor->new(@ARGV);
my $status = $processor->run();
exit $status;


# ----------------------------
package ExternalsProcessor;


sub new {
	my $self = shift;
	my %args = @_;
	
	my $class = ref($self) || $self;
	$self = bless \%args, $class;
# 	$self->init();
	return $self;
}


# sub init {
# 	my $self = shift;
# #	print $self->shell(qw(git --version)) . "\n";
# }


sub known_url {
	my $self = shift;
	my ($url) = @_;
	return $self->svn_url_for_current_dir() eq $url || $self->{parent} && $self->{parent}->known_url($url);
}


sub run {
	my $self = shift;

	my $dir = Cwd::cwd();
	
	$self->update_current_dir();
	$self->process_svn_ignore();

	my @externals = $self->read_externals();
	while (my $subdir = shift @externals) {
		my $url = shift @externals;
		die "Error: svn:externals cycle detected: '$url'\n" if $self->known_url($url);

		print "[$dir] updating SVN external: $subdir\n";

		die "Error: Unable to find or mkdir '$subdir'\n" unless (-e $subdir || File::Path::mkpath($subdir));
		die "Error: Expected '$subdir' to be a directory\n" unless (-d $subdir);

		die "Error: Unable to chdir to '$subdir'\n" unless chdir($subdir);
		# Recursively run a sub-processor for externals in the current directory
		die if $self->new(parent => $self, externals_url => $url)->run();
		die "Error: Unable to chdir back to '$dir'\n" unless chdir($dir);

		$self->update_ignore($subdir);
	}

	return 0;
}


sub update_current_dir {
	my $self = shift;

	my $dir = Cwd::cwd();
	
	my @contents = grep {!/^(?:\.+|\.DS_Store)$/} IO::Dir->new('.')->read();
	if (@contents == 0) {
		# first-time clone
		die "Error: Missing externals URL for '$dir'\n" unless $self->{externals_url};
		$self->shell(qw(git svn clone), $self->{externals_url}, '.');
	} elsif (@contents == 1 && $contents[0] eq '.git') {
		# interrupted clone, restart with fetch
		$self->shell(qw(git svn fetch));
	} else {
		# regular update, rebase to SVN head

		# Check that we're on the right branch
		my ($branch) = $self->shell(qw(git status)) =~ /On branch (\S+)/;
		die "Error: Unable to determine Git branch in '$dir'\n" unless $branch;
		die "Error: Git branch is '$branch', should be 'master' in '$dir'\n" unless ($branch eq 'master');

		# Check that there are no uncommitted changes in the working copy that would trip up git's svn rebase
		my @dirty = grep {!/^\?\?/} $self->shell(qw(git status --porcelain));
		die "Error: Can't run svn rebase with dirty files in '$dir':\n" . join('', map {"$_\n"} @dirty) if @dirty;

		# Check that the externals definition URL hasn't changed
		my $url = $self->svn_url_for_current_dir();
		if ($self->{externals_url} && $self->{externals_url} ne $url) {
			die "Error: The svn:externals URL for '$dir' is defined as\n\n  $self->{externals_url}\n\nbut the existing Git working copy in that directory is configured as\n\n  $url\n\nThe externals definition might have changed since the working copy was created. Remove the '$dir' directory and re-run this script to check out a new version from the new URL.\n";
		}

		# All sanity checks OK, perform the update
		$self->shell_echo(qw(git svn rebase));
	}
}


sub update_ignore {
	my $self = shift;
	my (@external_dir_paths) = @_;

	my @exclude_lines;
	my $ignore_path = '.git/info/exclude';
	my $ignore_file = IO::File->new($ignore_path);
	@exclude_lines = $ignore_file->getlines() if $ignore_file;
	chomp @exclude_lines;
	
	my @new_exclude_lines;
	foreach my $path (@external_dir_paths) {
		push @new_exclude_lines, $path unless (grep {$_ eq $path} (@exclude_lines, @new_exclude_lines));
	}

	return unless @new_exclude_lines;

	my $dir = Cwd::cwd();
	print "Updating Git ignored file list $dir/$ignore_path: @new_exclude_lines\n";
	
	$ignore_file = IO::File->new(">$ignore_path");
	die "Error: Unable to write-open '$ignore_path'\n" unless $ignore_file;
	$ignore_file->print(map {"$_\n"} (@exclude_lines, @new_exclude_lines));
}


sub read_externals {
	my $self = shift;

	my $dir = Cwd::cwd();

	my @externals =
		grep {!m%^\s*/?\s*#%}
		$self->shell(qw(git svn show-externals));

	my @versioned_externals = grep {/-r\d+\b/i} @externals;
	if (@versioned_externals) {
		die "Error: Found external(s) pegged to fixed revision: '@versioned_externals' in '$dir', don't know how to handle this.\n";
	}

	return map {m%^/(\S+)\s+(\S+)%; $1 ? ($1 => $2) : ()} @externals;
}


sub process_svn_ignore {
	my $self = shift;

	my @svn_ignored =
		map {m%^/(\S+)%; $1 ? $1 : ()}
		grep {!m%^\s*/?\s*#%}
		$self->shell(qw(git svn show-ignore));

	$self->update_ignore(@svn_ignored) if @svn_ignored;
}


sub svn_info_for_current_dir {
	my $self = shift;
	return {map {/^([^:]+): (.*)/} $self->shell(qw(git svn info))};
}


sub svn_url_for_current_dir {
	my $self = shift;
	my $url = $self->svn_info_for_current_dir()->{URL};
	my $dir = Cwd::cwd();
	die "Unable to determine SVN URL for '$dir'" unless $url;
	return $url;
}



sub shell {
	my $self = shift;
	my $dir = Cwd::cwd();
# 	print "shell ($dir): @_\n";
 	my @cmd = map {"'$_'"} @_;
 	my $output = qx(@cmd);
# 	my $output = qx(@cmd | tee /dev/stderr);
 	my $result = $? >> 8;
	die "Error: Nonzero exit status for command '@_' executed in '$dir'\n" if $result;
	my @lines = split(/\n/, $output);
	return wantarray ? @lines : $lines[0];
}


sub shell_echo {
	my $self = shift;
	my $dir = Cwd::cwd();
 	print "[$dir] shell: @_\n";
 	my @cmd = map {"'$_'"} @_;
 	my $output = qx(@cmd | tee /dev/stderr);
 	my $result = $? >> 8;
	die "Error: Nonzero exit status for command '@_'\n" if $result;
	my @lines = split(/\n/, $output);
	return wantarray ? @lines : $lines[0];
}

#!/usr/bin/perl
#
# Recursively clone svn:externals in a git-svn sandbox.
#
# Written by Marc Liyanage <http://www.entropy.ch>
#
# See http://github.com/liyanage/git-tools
#

use strict;
use warnings;

use Cwd;
use IO::Dir;
use File::Path;
use File::Basename;


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
	$self->init();
	return $self;
}


sub init {
	my $self = shift;
	$self->{svn_info} = {map {/^([^:]+): (.*)/} $self->shell(qw(git svn info))};
	$ENV{PATH} = "/opt/local/bin:$ENV{PATH}";
#	print $self->shell(qw(git --version)) . "\n";
}


sub known_url {
	my $self = shift;
	my ($url) = @_;
	return $self->{svn_info}->{URL} eq $url || $self->{parent} && $self->{parent}->known_url($url);
}


sub run {
	my $self = shift;

	my @externals = $self->read_externals();
	return 0 unless @externals;
	
	my $dir = Cwd::cwd();

	while (my $subdir = shift @externals) {
		my $url = shift @externals;
		die "svn:externals cycle detected: '$url'" if $self->known_url($url);

		print "$dir: $subdir\n";

		die "Unable to find or mkdir '$subdir'" unless (-e $subdir || File::Path::mkpath($subdir));
		die "Expected '$subdir' to be a directory" unless (-d $subdir);
		
		$self->update_external_dir($subdir, $url);
		$self->update_ignore($subdir);
	}

	$self->process_svn_ignore();

	return 0;
}


sub update_external_dir {
	my $self = shift;
	my ($external_dir_path, $url) = @_;
	
	my $dir = Cwd::cwd();

	die "Unable to chdir to '$external_dir_path'" unless chdir($external_dir_path);

	my @contents = grep {!/^\.+$/} IO::Dir->new('.')->read();
	if (@contents == 0) {
		# first-time clone
		$self->shell(qw(git svn clone), $url, '.');
	} elsif (@contents == 1 && $contents[0] eq '.git') {
		# interrupted clone, restart with fetch
		$self->shell(qw(git svn fetch));
	} else {
		# regular update, rebase to SVN head
		$self->shell(qw(git svn rebase));
	}

	# Recursively run a sub-processor for externals in the current directory
	die if $self->new(parent => $self)->run();

	die "Unable to chdir back to '$dir'" unless chdir($dir);
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
	die "Unable to write-open '$ignore_path'" unless $ignore_file;
	$ignore_file->print(map {"$_\n"} (@exclude_lines, @new_exclude_lines));
}


sub read_externals {
	my $self = shift;

	my $dir = Cwd::cwd();

	my @externals =
		grep {!m%^\s*/?\s*#%}
		$self->shell(qw(git svn show-externals));

	my @versioned_externals = grep {/\b-r\d+\b/i} @externals;
	if (@versioned_externals) {
		die "Found external(s) pegged to fixed revision: '@versioned_externals' in '$dir', don't know how to handle this.";
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


sub shell {
	my $self = shift;
	my $dir = Cwd::cwd();
# 	print "shell ($dir): @_\n";
 	my @cmd = map {"'$_'"} @_;
 	my $output = qx(@cmd);
# 	my $output = qx(@cmd | tee /dev/stderr);
 	my $result = $? >> 8;
	die "Nonzero exit status for command '@_'" if $result;
	my @lines = split(/\n/, $output);
	return wantarray ? @lines : $lines[0];
}

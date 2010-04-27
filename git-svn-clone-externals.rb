#!/usr/bin/ruby -w
#
# This script reads the svn:externals directory definitions of a git-svn
# working copy and performs a "git svn clone" for each directory.
# It then enters each one and repeats the process recursively,
# until there are no more svn:externals to resolve, thus creating the
# equivalent of what "svn checkout" would do.
#
# After the initial run, the script can be used to keep all of the 
# new working copies updated to SVN HEAD. You run it in the toplevel
# directory and it will perform a "git svn rebase" operation on the current
# directory, then descend into all externals directories and again repeat
# the process recursively.
#
# Features
# ========
#
# - Can restart aborted first-time clone operations. Just re-run the script.
# - Adds the exclude directories it creates to the .git/info/exclude list
#   so they don't show up in the status report.
# - Also adds items in svn:ignore properties to the .git/info/exclude list.
# - Discovers new svn:externals definitions during update runs and performs a clone operation.
# - Detects changed SVN URLs for an existing working copy and aborts with a warning.
# - Detects and lists git-svn working copies that don't correspond to svn:externals
#   definitions, which happens if an externals definition is removed.
# - Quick mode for updates (see below).
# - Detects svn:externals reference cycles.
#
# First-time usage for the initial setup
# ======================================
#
# 1.) First check out some SVN repository with git-svn:
#
#     git svn clone http://...
#
# 2.) Change directory to the new working copy and run the script:
#
#     git-svnclone-externals.rb
#
#     By default it checks out the complete history for each SVN
#     project it clones. This can take a long time and if you don't
#     want that, you can use the --no-history command line option.
#
# Update usage after initial setup
# ================================
#
# 1.) Change directory to the toplevel working copy
#
# 2.) Run the script as above
#
#     In this use case, the script has a "quick" mode that you can
#     activate with the "-q" command line option. If you use it, it
#     will not read the actual svn:externals definitions, but instead
#     search for the existing sub-working copies and just update those.
#     This mode will not pick up new or changed svn:externals definitions,
#     so you should run it in normal mode from time to time.
# 
# Restrictions for update mode:
#
# - The script assumes that all integration with the SVN repository
#   happens on the "master" git branch. If it encounters a working copy that
#   is on a different branch during its traversal, it will abort with an
#   error message.
# - The script will abort when it encounters working copies
#   with uncommitted changes.
#
# Written by Marc Liyanage <http://www.entropy.ch>
# See http://github.com/liyanage/git-tools for the newest version
#

require 'fileutils'

class ExternalsProcessor

  def initialize(options = {})
    @parent = options[:parent]
    @warnings = {} unless @parent
    @externals_url = options[:externals_url]
    @quick = options[:quick]
    @no_history = options[:no_history]
  end


  def run
    t1 = Time.now
    update_current_dir
    process_svn_ignore_for_current_dir unless quick?

    return 0 if @parent && quick?

    externals = read_externals
    process_externals(externals)

    find_non_externals_sandboxes(externals) unless quick?

    unless @parent
      dump_warnings
      puts "Total time: %ds" % (Time.now - t1)
    end

    0
  end


  def process_externals(externals)
    externals.each do |dir, url|
      raise "Error: svn:externals cycle detected: '#{url}'" if known_url?(url)
      raise "Error: Unable to find or mkdir '#{dir}'" unless File.exist?(dir) || FileUtils.mkpath(dir)
      raise "Error: Expected '#{dir}' to be a directory" unless File.directory?(dir)

      puts "[#{Dir.getwd}] updating external: #{dir}"
      Dir.chdir(dir) { self.class.new(:parent => self, :externals_url => url).run }
      update_exclude_file_with_paths(dir) unless quick?
    end
  end

  
  def dump_warnings
    @warnings.each do |key, data|
      puts "Warning: #{data[:message]}:"
      data[:items].each { |x| puts "#{x}\n" }
    end
  end


  def find_non_externals_sandboxes(externals)
    externals_dirs = externals.map { |x| x[0] }
    sandboxes = find_git_svn_sandboxes_in_current_dir
    non_externals_sandboxes = sandboxes.select { |sandbox| externals_dirs.select { |external| sandbox.index(external) == 0}.empty? }
    return if non_externals_sandboxes.empty?
    collect_warning('unknown_sandbox', 'Found git-svn sandboxes that do not correspond to SVN externals', non_externals_sandboxes.map {|x| "#{Dir.getwd}/#{x}"})
#    puts "Warning: Found git-svn sandboxes that do not correspond to SVN externals:"
  end


  def collect_warning(category, message, items)
    if @parent
      @parent.collect_warning(category, message, items)
      return
    end
    @warnings[category] ||= {:message => message, :items => []}
    @warnings[category][:items].concat(items)
  end


  def update_current_dir
    wd = Dir.getwd
    contents = Dir.entries('.').reject { |x| x =~ /^(?:\.+|\.DS_Store)$/ }

    if contents.empty?
      # first-time clone
      raise "Error: Missing externals URL for '#{wd}'" unless @externals_url
      no_history_option = no_history? ? '-r HEAD' : ''
      shell("git svn clone #{no_history_option} #@externals_url .")
    elsif contents == ['.git']
      # interrupted clone, restart with fetch
      shell('git svn fetch')
    else
      # regular update, rebase to SVN head

      # Check that we're on the right branch
      shell('git status')[0] =~ /On branch (\S+)/
      raise "Error: Unable to determine Git branch in '#{wd}' using 'git status'" unless $~
      branch = $~[1]
      raise "Error: Git branch is '#{branch}', should be 'master' in '#{wd}'\n" unless branch == 'master'

      # Check that there are no uncommitted changes in the working copy that would trip up git's svn rebase
      dirty = shell('git status --porcelain').reject { |x| x =~ /^\?\?/ }
      raise "Error: Can't run svn rebase with dirty files in '#{wd}':\n#{dirty.map {|x| x + "\n"}}" unless dirty.empty?

      # Check that the externals definition URL hasn't changed
      if !quick?
        url = svn_url_for_current_dir
        if @externals_url && @externals_url != url
          raise "Error: The svn:externals URL for '#{wd}' is defined as\n\n  #@externals_url\n\nbut the existing Git working copy in that directory is configured as\n\n  #{url}\n\nThe externals definition might have changed since the working copy was created. Remove the '#{wd}' directory and re-run this script to check out a new version from the new URL.\n"
        end
      end

      # All sanity checks OK, perform the update
      shell_echo('git svn rebase')
    end

  end


  def read_externals
    return read_externals_quick if quick?
    externals = shell('git svn show-externals').reject { |x| x =~ %r%^\s*/?\s*#% }
    versioned_externals = externals.grep(/-r\d+\b/i)
    unless versioned_externals.empty?
      raise "Error: Found external(s) pegged to fixed revision: '#{versioned_externals.join ', '}' in '#{Dir.getwd}', don't know how to handle this."
    end
    externals.grep(%r%^/(\S+)\s+(\S+)%) { $~[1,2] }
  end


  # In quick mode, fake it by using "find"
  def read_externals_quick
    find_git_svn_sandboxes_in_current_dir.map {|x| [x, nil]}
  end
  
  def find_git_svn_sandboxes_in_current_dir
    %x(find . -type d -name .git).split("\n").select {|x| File.exist?("#{x}/svn")}.grep(%r%^./(.+)/.git$%) {$~[1]}
  end
  

  def process_svn_ignore_for_current_dir
    svn_ignored = shell('git svn show-ignore').reject { |x| x =~ %r%^\s*/?\s*#% }.grep(%r%^/(\S+)%) { $~[1] }
    update_exclude_file_with_paths(svn_ignored) unless svn_ignored.empty?
  end


  def update_exclude_file_with_paths(excluded_paths)
    excludefile_path = '.git/info/exclude'
    exclude_lines = []
    File.open(excludefile_path) { |file| exclude_lines = file.readlines.map { |x| x.chomp } } if File.exist?(excludefile_path)
    
    new_exclude_lines = []
    excluded_paths.each do |path|
      new_exclude_lines.push(path) unless (exclude_lines | new_exclude_lines).include?(path)
    end

    return if new_exclude_lines.empty?

    puts "Updating Git exclude list '#{Dir.getwd}/#{excludefile_path}' with new items: #{new_exclude_lines.join(" ")}\n"
    File.open(excludefile_path, 'w') { |file| file << (exclude_lines + new_exclude_lines).map { |x| x + "\n" } }
  end


  def svn_info_for_current_dir
    svn_info = {}
    shell('git svn info').map { |x| x.split(': ') }.each { |k, v| svn_info[k] = v }
    svn_info
  end


  def svn_url_for_current_dir
    url = svn_info_for_current_dir['URL']
    raise "Unable to determine SVN URL for '#{Dir.getwd}'" unless url
    url
  end


  def known_url?(url)
    return false if quick?
    url == svn_url_for_current_dir || (@parent && @parent.known_url?(url))
  end
  
  def quick?
    return (@parent && @parent.quick?) || @quick
  end

  def no_history?
    return (@parent && @parent.no_history?) || @no_history
  end

  def shell(cmd)
    t1 = Time.now
    list = %x(#{cmd}).split("\n")
    dt = (Time.now - t1).to_f
    status = $? >> 8
    raise "[#{Dir.getwd}] Non-zero exit status #{status} for command '#{cmd}'" if status != 0
#    puts "[shell %.2fs %s] %s" % [dt, Dir.getwd, cmd]
    list
  end


  def shell_echo(cmd)
    t1 = Time.now
    list = %x(#{cmd} | tee /dev/stderr).split("\n")
    dt = (Time.now - t1).to_f
    status = $? >> 8
    raise "[#{Dir.getwd}] Non-zero exit status #{status} for command '#{cmd}'" if status != 0
#    puts "[shell %.2fs %s] %s" % [dt, Dir.getwd, cmd]
    list
  end

end


# ----------------------

ENV['PATH'] = "/opt/local/bin:#{ENV['PATH']}"
quick = ARGV.delete('-q')
no_history = ARGV.delete('--no-history')
puts "Quick mode" if quick
puts "Skip history" if no_history
exit ExternalsProcessor.new(:quick => quick, :no_history => no_history).run
